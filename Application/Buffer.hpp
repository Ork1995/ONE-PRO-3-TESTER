/*
 * Buffer.hpp
 *
 *  Created on: Mar 27, 2025
 *      Author: Igor
 */

#pragma once

#include <BufferView.hpp>
#include <string.h>

template <int Capacity, typename TItem = char>
class Buffer: public BufferView<TItem>
{
public:
	using TBase = BufferView<TItem>;
	static constexpr int CAPACITY = Capacity;

	Buffer(): TBase(Capacity, _buf, 0) {}

	Buffer(const TBase &other): TBase(Capacity, _buf, 0) {
		TBase::Append(other);
	}

private:
	TItem _buf[Capacity];
};
