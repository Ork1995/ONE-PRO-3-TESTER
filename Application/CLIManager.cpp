/*
 * CLIManager.cpp
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */

#include <CLIManager.h>
#include "cmsis_os.h"

CLIManager::CLIManager(Uart &uart): _uart(uart)
{
	// TODO: Create task
}

void CLIManager::Task()
{
	for(;;)
	{
		// TODO: Read synchronously from UART and handle commands
		osDelay(1);
	}
}
