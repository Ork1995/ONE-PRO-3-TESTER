/*
 * MutexLock.cpp
 *
 *  Created on: Mar 27, 2025
 *      Author: Igor
 */

#include <MutexLock.hpp>

MutexLock::MutexLock(osMutexId_t mutex): _mutex(mutex)
{
	osMutexAcquire(mutex, osWaitForever);
}

MutexLock::~MutexLock()
{
	osMutexRelease(_mutex);
}
