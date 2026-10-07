################################################################################
# Automatically-generated file. Do not edit!
# Toolchain: GNU Tools for STM32 (14.3.rel1)
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
CPP_SRCS += \
../Application/App.cpp \
../Application/Board.cpp \
../Application/CLIManager.cpp \
../Application/Clock.cpp \
../Application/Comm.cpp \
../Application/DacControl.cpp \
../Application/DigitalOutput.cpp \
../Application/MutexLock.cpp \
../Application/RealTimer.cpp \
../Application/SensorSupply.cpp \
../Application/TextPrinter.cpp \
../Application/TextScanner.cpp \
../Application/Uart.cpp \
../Application/ValveDetector.cpp \
../Application/WaterMeterSimulator.cpp \
../Application/appProxy.cpp 

OBJS += \
./Application/App.o \
./Application/Board.o \
./Application/CLIManager.o \
./Application/Clock.o \
./Application/Comm.o \
./Application/DacControl.o \
./Application/DigitalOutput.o \
./Application/MutexLock.o \
./Application/RealTimer.o \
./Application/SensorSupply.o \
./Application/TextPrinter.o \
./Application/TextScanner.o \
./Application/Uart.o \
./Application/ValveDetector.o \
./Application/WaterMeterSimulator.o \
./Application/appProxy.o 

CPP_DEPS += \
./Application/App.d \
./Application/Board.d \
./Application/CLIManager.d \
./Application/Clock.d \
./Application/Comm.d \
./Application/DacControl.d \
./Application/DigitalOutput.d \
./Application/MutexLock.d \
./Application/RealTimer.d \
./Application/SensorSupply.d \
./Application/TextPrinter.d \
./Application/TextScanner.d \
./Application/Uart.d \
./Application/ValveDetector.d \
./Application/WaterMeterSimulator.d \
./Application/appProxy.d 


# Each subdirectory must supply rules for building sources it contributes
Application/%.o Application/%.su Application/%.cyclo: ../Application/%.cpp Application/subdir.mk
	arm-none-eabi-g++ "$<" -mcpu=cortex-m4 -std=gnu++14 -g3 -DDEBUG -DUSE_HAL_DRIVER -DSTM32L496xx -c -I../Application -I../Core/Inc -I../Drivers/STM32L4xx_HAL_Driver/Inc -I../Drivers/STM32L4xx_HAL_Driver/Inc/Legacy -I../Middlewares/Third_Party/FreeRTOS/Source/include -I../Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS_V2 -I../Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F -I../Drivers/CMSIS/Device/ST/STM32L4xx/Include -I../Drivers/CMSIS/Include -O0 -ffunction-sections -fdata-sections -fno-exceptions -fno-rtti -fno-use-cxa-atexit -Wall -fstack-usage -fcyclomatic-complexity -MMD -MP -MF"$(@:%.o=%.d)" -MT"$@" --specs=nano.specs -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb -o "$@"

clean: clean-Application

clean-Application:
	-$(RM) ./Application/App.cyclo ./Application/App.d ./Application/App.o ./Application/App.su ./Application/Board.cyclo ./Application/Board.d ./Application/Board.o ./Application/Board.su ./Application/CLIManager.cyclo ./Application/CLIManager.d ./Application/CLIManager.o ./Application/CLIManager.su ./Application/Clock.cyclo ./Application/Clock.d ./Application/Clock.o ./Application/Clock.su ./Application/Comm.cyclo ./Application/Comm.d ./Application/Comm.o ./Application/Comm.su ./Application/DacControl.cyclo ./Application/DacControl.d ./Application/DacControl.o ./Application/DacControl.su ./Application/DigitalOutput.cyclo ./Application/DigitalOutput.d ./Application/DigitalOutput.o ./Application/DigitalOutput.su ./Application/MutexLock.cyclo ./Application/MutexLock.d ./Application/MutexLock.o ./Application/MutexLock.su ./Application/RealTimer.cyclo ./Application/RealTimer.d ./Application/RealTimer.o ./Application/RealTimer.su ./Application/SensorSupply.cyclo ./Application/SensorSupply.d ./Application/SensorSupply.o ./Application/SensorSupply.su ./Application/TextPrinter.cyclo ./Application/TextPrinter.d ./Application/TextPrinter.o ./Application/TextPrinter.su ./Application/TextScanner.cyclo ./Application/TextScanner.d ./Application/TextScanner.o ./Application/TextScanner.su ./Application/Uart.cyclo ./Application/Uart.d ./Application/Uart.o ./Application/Uart.su ./Application/ValveDetector.cyclo ./Application/ValveDetector.d ./Application/ValveDetector.o ./Application/ValveDetector.su ./Application/WaterMeterSimulator.cyclo ./Application/WaterMeterSimulator.d ./Application/WaterMeterSimulator.o ./Application/WaterMeterSimulator.su ./Application/appProxy.cyclo ./Application/appProxy.d ./Application/appProxy.o ./Application/appProxy.su

.PHONY: clean-Application

