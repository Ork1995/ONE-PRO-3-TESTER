/*
 * TextPrinter.cpp
 *
 *  Created on: Apr 2, 2025
 *      Author: Igor
 */

#include <TextPrinter.hpp>
#include <stdio.h>
#include <string.h>

TextPrinter::TextPrinter(BufferView<char> &text):
	_text(text)
{
}

TextPrinter& TextPrinter::operator << (const BufferView<char> &str)
{
	_text.Append(str);
	return *this;
}

TextPrinter& TextPrinter::operator << (const char *str)
{
	_text.Append(str, strlen(str));
	return *this;
}

TextPrinter& TextPrinter::operator << (long number)
{
	char buf[30];
	int len = snprintf(buf, sizeof(buf), "%ld", number);
	_text.Append(buf, len);
	return *this;
}

TextPrinter& TextPrinter::operator << (Hex number)
{
	char buf[30];
	int len = snprintf(buf, sizeof(buf), "0x%X", (unsigned) number);
	_text.Append(buf, len);
	return *this;
}
