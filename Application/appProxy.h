#pragma once

#ifdef __cplusplus
#include "Board.hpp"
extern "C" {
#endif

void runAppTask(void);

#ifdef __cplusplus
}

Board &getBoard();
#endif
