/*
 * Uart.hpp
 *
 *  Created on: Mar 27, 2025
 *      Author: Igor
 */

#pragma once

#include "usart.h"
#include "Buffer.hpp"

class Uart
{
public:
	static constexpr int TxBufferSize = 512;
	static constexpr int RxBufferSize = 512;

	Uart(UART_HandleTypeDef &huart);

	/**
	 * @brief Send data to UART asynchronously by DMA (can block if there is previous data not sent yet)
	 * @param txBuf - buffer of data to send
	 * @return true if sending
	 */
	bool Send(const BufferView<uint8_t> &txBuf);

	/**
	 * @brief Non-blocking UART receive
	 * @param rxBuf On output contains received bytes
	 * @param nReceive bytes to receive
	 * @return Number of received bytes
	 */
	int Recv(uint8_t *rxBuf, int nReceive);

	/**
	 * @brief Must be called on start and on error
	 */
	void Restart();

	const UART_HandleTypeDef *GetPort() const { return &_huart; }

private:
	UART_HandleTypeDef &_huart;

	// DMA buffers
	Buffer<TxBufferSize, uint8_t> _txBuffer;
	Buffer<RxBufferSize, uint8_t> _rxBuffer;
	uint32_t _rxLastNDTR;

	HAL_StatusTypeDef _rxDmaStatus;
};
