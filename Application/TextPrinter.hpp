/*
 * TextPrinter.hpp
 *
 *  Created on: Apr 2, 2025
 *      Author: Igor
 */

#pragma once

#include "BufferView.hpp"
#include <stdint.h>

enum Hex: uint32_t
{
};

class TextPrinter
{
public:
	TextPrinter(BufferView<char> &text);
	TextPrinter& operator << (const BufferView<char> &str);
	TextPrinter& operator << (const char *str);
	TextPrinter& operator << (long number);
	TextPrinter& operator << (Hex number);

private:
	BufferView<char> &_text;
};
