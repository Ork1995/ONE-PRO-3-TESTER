/*
 * TextScanner.cpp
 *
 *  Created on: Apr 2, 2025
 *      Author: Igor
 */

#include <TextScanner.hpp>
#include <ctype.h>
#include <stdlib.h>
#include <Buffer.hpp>

TextScanner::TextScanner(const BufferView<char> &text):
	_text(text), _position(0), _error(false)
{
}

TextScanner& TextScanner::operator >> (BufferView<char> &token)
{
	if (_error) {
		return *this;
	}

	SkipWhitespace();

	// Save token
	while (_position < _text.Len()) {
		if (isspace(_text[_position])) {
			break;
		}
		token.Append(_text[_position++]);
	}

	return *this;
}

TextScanner& TextScanner::operator >> (long &number)
{
	if (_error) {
		return *this;
	}

	SkipWhitespace();

	Buffer<30> token;
	bool isHex = false;

	// Save number text
	while (_position < _text.Len()) {
		char c = tolower (_text [_position]);
		if (c == 'x' && token.Len () == 1 && token [0] == '0') {
			isHex = true;
		}
		else if (isHex) {
			if (!isdigit (c) && (c < 'a' || c > 'f')) {
				break;
			}
		}
		else {
			if (!isdigit (c) && !(c == '-' && token.Len () == 0)) {
				break;
			}
		}
		token.Append (c);
		++_position;
	}

	token.Append('\0');

	char *endPtr = 0;
	number = strtol(token, &endPtr, 0);
	_error = (char *) token == endPtr;

	return *this;
}

TextScanner& TextScanner::operator >> (const char *str)
{
	if (_error) {
		return *this;
	}

	SkipWhitespace();

	// Compare text with specified string
	while (_position < _text.Len() && *str) {
		if (_text[_position] != *str) {
			_error = true;
			return *this;
		}
		++_position;
		++str;
	}

	_error = *str != '\0';
	return *this;
}

void TextScanner::SkipWhitespace()
{
	// Skip whitespace
	while (_position < _text.Len()) {
		if (!isspace(_text[_position])) {
			break;
		}
		++_position;
	}
}
