/*
 * TextBuffer.hpp
 *
 *  Created on: Apr 2, 2025
 *      Author: Igor
 */

#pragma once

#include "BufferView.hpp"

class TextScanner
{
public:
	TextScanner(const BufferView<char> &text);

	/**
	 * Scan for next token
	 * @param token - on exit contains found token
	 * @return this
	 */
	TextScanner& operator >> (BufferView<char> &token);

	/**
	 * Scan for next number
	 * @param number - on exit contains found number (if any)
	 * @return this
	 */
	TextScanner& operator >> (long &number);

	/**
	 * Check that next text is specified text
	 * @param str - specified text
	 * @return this
	 */
	TextScanner& operator >> (const char *str);

	/**
	 * Return error state
	 * @return true if some previous scans were invalid
	 */
	bool IsError() const { return _error; }

private:
	const BufferView<char> &_text;
	int _position;
	bool _error;

	void SkipWhitespace();
};
