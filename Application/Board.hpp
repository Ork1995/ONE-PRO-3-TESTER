/*
 * Board.hpp
 *
 *  Created on: Apr 3, 2025
 *      Author: Igor
 */

#pragma once

#include "Uart.hpp"

class Board
{
public:
	Board();

	Uart *GetUart(UART_HandleTypeDef *huart);

	// TODO: UART to be defined
	//Uart _cliUart;
	Uart _commUart;
};
