/*
 * MutexLock.hpp
 *
 *  Created on: Mar 27, 2025
 *      Author: Igor
 */

#pragma once

#include "cmsis_os.h"

class MutexLock
{
public:
	MutexLock(osMutexId_t mutex);
	virtual ~MutexLock();

private:
	osMutexId_t _mutex;
};
