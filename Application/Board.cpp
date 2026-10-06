/*
 * Board.cpp
 *
 *  Created on: Apr 3, 2025
 *      Author: Igor
 */

#include <Board.hpp>
#include "usart.h"

Board::Board():
	_commUart { huart2 }
{
}

Uart *Board::GetUart(UART_HandleTypeDef *huart)
{
	if (_commUart.GetPort() == huart) {
		return &_commUart;
	}

	return nullptr;
}
