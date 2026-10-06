/*
 * Buffer.hpp
 *
 *  Created on: Mar 27, 2025
 *      Author: Igor
 */

#pragma once

#include <algorithm>

template <typename TItem = char>
class BufferView
{
public:
	BufferView(int capacity, TItem *pBuf, int len = 0): _capacity(capacity), _pBuf(pBuf), _len(len)  {}

	int Len() const { return _len; }
	int Capacity() const { return _capacity; }

	void Reset() { _len = 0; }
	void SetLen(int len) { len = std::max(0, std::min(_capacity, len)); }

	void Append (const TItem &item) {
		if (_len < _capacity) {
			_pBuf[_len++] = item;
		}
	}

	void Append(const BufferView<TItem> &items)
	{
		for (int i = 0; i < items.Len(); ++i) {
			Append(items[i]);
		}
	}

	void Append(const TItem *pItems, int len)
	{
		for (int i = 0; i < len; ++i) {
			Append(pItems[i]);
		}
	}

	TItem &operator [] (int index) {
		return _pBuf[index];
	}

	const TItem &operator [] (int index) const {
		return _pBuf[index];
	}

	operator TItem * () {
		return _pBuf;
	}

	operator const TItem * () const {
		return _pBuf;
	}

	TItem *begin() {
		return _pBuf;
	}

	const TItem *begin() const {
		return _pBuf;
	}

	TItem *end() {
		return _pBuf + _len;
	}

	const TItem *end() const {
		return _pBuf + _len;
	}

	template <typename TOtherItem, typename = std::enable_if_t<sizeof(TItem) == sizeof(TOtherItem)>>
	operator const BufferView<TOtherItem> & () const {
		return reinterpret_cast<const BufferView<TOtherItem> &> (*this);
	}

	void operator = (const BufferView<TItem> &other) {
		Reset();
		Append(other);
	}

	bool operator == (const TItem *pRaw) {
		if (!pRaw) return !_pBuf;
		for (int i = 0; i < _len; ++i) {
			if (!pRaw[i]) return false;
			if (_pBuf[i] != pRaw[i]) return false;
		}
		return !pRaw[_len];
	}

	bool operator != (const TItem *pRaw) {
		return !(*this == pRaw);
	}

protected:
	int _capacity;
	TItem *_pBuf;
	int _len;
};
