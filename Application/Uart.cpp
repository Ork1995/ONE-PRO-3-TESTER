/*
 * Uart.cpp
 *
 *  Created on: Mar 27, 2025
 *      Author: Igor
 */

#include "Uart.hpp"
#include "Clock.hpp"
#include "appProxy.h"
#include "cmsis_os.h"
#include <algorithm>

Uart::Uart(UART_HandleTypeDef &huart):
	_huart(huart),
	_rxLastNDTR(0)
{
	_txBuffer.SetLen(_txBuffer.CAPACITY);
	_rxBuffer.SetLen(_rxBuffer.CAPACITY);
	Restart();
}

void Uart::Restart()
{
	// Start circular DMA receive
	_rxLastNDTR = _rxBuffer.CAPACITY;
	_rxDmaStatus = HAL_UART_Receive_DMA(&_huart, _rxBuffer, _rxBuffer.CAPACITY);
}

bool Uart::Send(const BufferView<uint8_t> &txBuf)
{
	if (txBuf.Len() <= 0) {
		return true;
	}

	// The current CubeMX-generated USART2 configuration includes RX DMA only.
	// Use blocking transmit to match the actual board setup and avoid assuming
	// a TX DMA channel that is not configured in the hardware description.
	uint32_t now = Clock::GetTimeMsec();
	while (_huart.gState != HAL_UART_STATE_READY &&
			Clock::GetTimeMsec() - now < 100)
	{
		osDelay(1);
	}

	HAL_StatusTypeDef status = HAL_UART_Transmit(&_huart,
		txBuf.begin(),
		txBuf.Len(),
		100);

	return status == HAL_OK;
}

int Uart::Recv(uint8_t *rxBuf, int nReceive)
{
	int recvCount = 0;

	uint32_t ndtr = _huart.hdmarx->Instance->CNDTR;

	for (int i = 0; i < nReceive; ++i) {
		if (_rxLastNDTR == ndtr) {
			break;
		}

		int index = _rxBuffer.CAPACITY - _rxLastNDTR;
		rxBuf[i] = _rxBuffer[index];
		
		if (--_rxLastNDTR == 0) {
			_rxLastNDTR = _rxBuffer.CAPACITY;
		}
		++recvCount;
	}

	return recvCount;
}

extern "C" void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
	if (huart->ErrorCode == HAL_UART_ERROR_FE) {
		__HAL_UART_CLEAR_FEFLAG(huart);

		if (huart->hdmarx->State == HAL_DMA_STATE_READY) {
			Uart *pUart = getBoard().GetUart(huart);
			if (pUart) {
				pUart->Restart();
			}
		}
	}

	// TODO: Handle other errors: overrun etc.
}
