/*
 * Clock.cpp
 *
 *  Created on: Apr 2, 2025
 *      Author: Igor
 */

#include "Clock.hpp"
#include <cmsis_os2.h>
#include <FreeRTOS.h>

namespace Clock
{

uint32_t GetTimeMsec()
{
	return osKernelGetTickCount() * (1000 / configTICK_RATE_HZ); // HAL_GetTick()

}

}
