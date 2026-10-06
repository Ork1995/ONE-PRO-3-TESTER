/*
 * CLIManager.h
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */

#pragma once

#include "Uart.hpp"

class CLIManager
{
public:
	static const int MAX_CMD_LEN = 256;

	CLIManager(Uart &uart);
	void Task();

private:
	Uart &_uart;
};
