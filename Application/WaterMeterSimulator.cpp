/*
 * WaterMeterSimulator.cpp
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */
#include <WaterMeterSimulator.hpp>
#include "Clock.hpp"

// Duty-cycle configuration: 5% ON, 95% OFF
static constexpr uint32_t PULSE_ON_PERCENT  = 5;
static constexpr uint32_t PULSE_OFF_PERCENT = 95;

/**
 * @brief Sets the GPIO output pin to HIGH or LOW and updates the internal state.
 * @param isHigh true = HIGH, false = LOW
 */
void WaterMeterSimulator::Set(bool isHigh)
{
    _isHigh = isHigh;
    HAL_GPIO_WritePin(_port, _pin, (GPIO_PinState) isHigh);
}

void WaterMeterSimulator::SetManualHigh()
{
    _status = Status::ManualHigh;
    Set(true);
}

/**
 * Updates the simulator status and recalculates the pulse timings.
 *
 * The ON time  = cycleTimeMs * PULSE_ON_PERCENT  / 100  (stored in _periodMs)
 * The OFF time = cycleTimeMs * PULSE_OFF_PERCENT / 100  (= _cycleTimeMs - _periodMs)
 *
 * Example: cycleTimeMs=1000, PULSE_ON_PERCENT=5 → 50ms ON / 950ms OFF.
 *
 * _tLastSwitch is reset whenever the status changes OR when only the cycle time
 * changes, to prevent an immediate erroneous pulse trigger after the update.
 *
 * @param status       New desired status
 * @param cycleTimeMs  Full cycle duration in milliseconds (ON + OFF)
 */
void WaterMeterSimulator::SetStatus(Status status, uint32_t cycleTimeMs)
{
    uint32_t onTimeMs    = cycleTimeMs ? (cycleTimeMs * PULSE_ON_PERCENT / 100) : 0xFFFFFFFF;
    uint32_t offTimeMs   = cycleTimeMs ? (cycleTimeMs - onTimeMs)                 : 0xFFFFFFFF;
    uint32_t newPeriodMs = onTimeMs;   // _periodMs stores the ON duration
    (void)offTimeMs;                   // used below via _cycleTimeMs - _periodMs
    bool statusChanged  = (_status != status);
    bool periodChanged  = (_cycleTimeMs != cycleTimeMs);
    bool wasRunning     = (_status == Status::Started || _status == Status::RunningTriggered);
    bool willRun        = (status  == Status::Started || status  == Status::RunningTriggered);

    if (statusChanged) {
        if (wasRunning) {
            // ---- Save state for mid-cycle resume ----
            // How long has the current half-period been running?
            uint32_t elapsed = Clock::GetTimeMsec() - _tLastSwitch;
            _savedIsHigh = _isHigh;
            uint32_t currentPhaseMs = _isHigh ? _periodMs : (_cycleTimeMs - _periodMs);
            _resumeRemainingMs = (elapsed < currentPhaseMs) ? (currentPhaseMs - elapsed) : 0;
            _hasResumeState    = true;
        }

        _status = status;

        if (willRun) {
            uint32_t tNow = Clock::GetTimeMsec();
            // Resume only if we have saved state AND the cycle time hasn't changed
            bool canResume = _hasResumeState && (_resumeRemainingMs > 0) && !periodChanged;
            if (canResume) {
                // Restore the pin phase and back-date _tLastSwitch so that the
                // next toggle fires exactly after the remaining time
                Set(_savedIsHigh);
                uint32_t resumePhaseMs = _savedIsHigh ? newPeriodMs : (cycleTimeMs - newPeriodMs);
                _tLastSwitch = tNow - (resumePhaseMs - _resumeRemainingMs);
                _resumeRemainingMs = 0;
            } else {
                // First start ever, or cycle time changed — begin fresh from LOW
                Set(false);
                _tLastSwitch = tNow;
            }
        } else {
            Set(false);
            _tLastSwitch = Clock::GetTimeMsec();
        }
    }
    else if (periodChanged) {
        // Status unchanged but cycle time updated — reset timing reference to
        // avoid a spurious immediate toggle on the next Task() call
        _tLastSwitch = Clock::GetTimeMsec();
    }

    // Preserve the last running cycle time when stopping with cycleTimeMs=0
    // (App.cpp passes 0 on stop, which would corrupt the resume state check)
    if (cycleTimeMs != 0) {
        _cycleTimeMs = cycleTimeMs;
        _periodMs    = newPeriodMs;
    }
}

/**
 * @brief Prints the current status of this water meter simulator.
 * @param printer  Reference to a TextPrinter output object
 */
void WaterMeterSimulator::PrintStatus(TextPrinter &printer)
{
    printer << " wm " << _id << " ";

    switch (_status) {
    case Status::Started:
        printer << "started";
        break;
    case Status::Stopped:
        printer << "stopped";
        break;
    case Status::Triggered:
        printer << "triggered";
        break;
    case Status::RunningTriggered:
        printer << "running (triggered)";
        break;
    case Status::ManualHigh:
        printer << "manual on";
        break;
    default:
        printer << "unknown";
    }

    printer << " " << _cycleTimeMs << "ms";
}

/**
 * @brief Main task function — must be called periodically (e.g. from a scheduler or main loop).
 *
 * Handles pulse generation based on the current status:
 *  - Started:          Generates pulses at the configured rate regardless of valve state.
 *  - Triggered:        Waits for valves to open, then transitions to RunningTriggered.
 *  - RunningTriggered: Generates pulses while valves are open; stops when valves close.
 *  - Stopped:          No action taken.
 *
 * Pulse counting: _pulseCount is incremented on the rising edge (LOW→HIGH transition).
 *
 * Timing note: _tLastSwitch is incremented by _periodMs (not set to tNow) to prevent
 * drift accumulation over time, ensuring accurate long-term pulse frequency.
 *
 * @param isValvesOpened  true if the associated valves are currently open
 * @return StateChange::Started if the simulator just began running,
 *         StateChange::Stopped if it just stopped,
 *         StateChange::None    otherwise
 */
WaterMeterSimulator::StateChange WaterMeterSimulator::Task(bool isValvesOpened)
{
    StateChange change = StateChange::None;

    if (_status == Status::Started) {
        // Free-running pulse generation — independent of valve state
        uint32_t tNow     = Clock::GetTimeMsec();
        uint32_t onTimeMs = _periodMs;
        uint32_t offTimeMs = _cycleTimeMs - _periodMs;
        uint32_t currentPhaseMs = _isHigh ? onTimeMs : offTimeMs;
        if (tNow - _tLastSwitch >= currentPhaseMs) {
            _tLastSwitch += currentPhaseMs;  // Increment by fixed phase to avoid drift
            Set(!_isHigh);

            // Count rising edges only (LOW→HIGH = one complete pulse registered)
            if (_isHigh) _pulseCount++;
        }
    }
    else if (_status == Status::Triggered) {
        // Waiting for valves to open before starting pulse generation
        if (isValvesOpened) {
            SetStatus(Status::RunningTriggered, _cycleTimeMs);
            change = StateChange::Started;
        }
    }
    else if (_status == Status::RunningTriggered) {
        if (!isValvesOpened) {
            // Valves closed — stop pulsing and revert to Triggered (waiting) state
            SetStatus(Status::Triggered, _cycleTimeMs);
            change = StateChange::Stopped;
        }
        else {
            // Valves open — generate pulses at the configured rate
            uint32_t tNow      = Clock::GetTimeMsec();
            uint32_t onTimeMs  = _periodMs;
            uint32_t offTimeMs = _cycleTimeMs - _periodMs;
            uint32_t currentPhaseMs = _isHigh ? onTimeMs : offTimeMs;
            if (tNow - _tLastSwitch >= currentPhaseMs) {
                _tLastSwitch += currentPhaseMs;  // Increment by fixed phase to avoid drift
                Set(!_isHigh);

                // Count rising edges only (LOW→HIGH = one complete pulse registered)
                if (_isHigh) _pulseCount++;
            }
        }
    }

    return change;
}