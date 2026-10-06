#include "appProxy.h"
#include "App.hpp"

extern "C" {

void runAppTask(void)
{
	App::Instance().Task();
}

}

Board &getBoard()
{
	return App::Instance().GetBoard();
}
