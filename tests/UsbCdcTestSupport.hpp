#pragma once

#include <cstdint>
#include <cstddef>

using BaseType_t = int;
using UBaseType_t = unsigned;
using StackType_t = uint32_t;
using TaskHandle_t = void *;
struct StaticTask_t { uint32_t unused; };
struct StaticSemaphore_t { uint32_t count; };
using osThreadId_t = void *;
using osSemaphoreId_t = StaticSemaphore_t *;
using osMutexId_t = StaticSemaphore_t *;
using osPriority_t = int;
constexpr int osPriorityNormal = 24;
constexpr int osPriorityBelowNormal = 16;
constexpr int osOK = 0;
constexpr uint32_t osWaitForever = UINT32_MAX;
constexpr int pdFALSE = 0;
constexpr int pdTRUE = 1;
struct osThreadAttr_t {
	const char *name;
	uint32_t attr_bits;
	void *cb_mem;
	uint32_t cb_size;
	void *stack_mem;
	uint32_t stack_size;
	osPriority_t priority;
	uint32_t tz_module;
	uint32_t reserved;
};
struct osSemaphoreAttr_t { const char *name; uint32_t attr_bits; void *cb_mem; uint32_t cb_size; };
using osMutexAttr_t = osSemaphoreAttr_t;
osThreadId_t osThreadNew(void (*entry)(void *), void *argument, const osThreadAttr_t *attributes);
osSemaphoreId_t osSemaphoreNew(uint32_t maximum, uint32_t initial, const osSemaphoreAttr_t *attributes);
osMutexId_t osMutexNew(const osMutexAttr_t *attributes);
int osSemaphoreAcquire(osSemaphoreId_t semaphore, uint32_t timeout);
int osSemaphoreRelease(osSemaphoreId_t semaphore);
int osMutexAcquire(osMutexId_t mutex, uint32_t timeout);
int osMutexRelease(osMutexId_t mutex);
void osDelay(uint32_t delay);
inline UBaseType_t portSET_INTERRUPT_MASK_FROM_ISR() { return 0; }
inline void portCLEAR_INTERRUPT_MASK_FROM_ISR(UBaseType_t) {}
extern bool fakeInterrupt;
inline uint32_t __get_IPSR() { return fakeInterrupt ? 1 : 0; }
inline void vTaskNotifyGiveFromISR(TaskHandle_t, BaseType_t *) {}
inline void xTaskNotifyGive(TaskHandle_t) {}
inline uint32_t ulTaskNotifyTake(int, uint32_t) { return 0; }
#define portYIELD_FROM_ISR(woken) ((void)(woken))
#define pdMS_TO_TICKS(ticks) (ticks)
#define UNUSED(value) ((void)(value))

constexpr uint8_t USBD_OK = 0;
constexpr uint8_t USBD_BUSY = 1;
constexpr uint8_t USBD_FAIL = 2;
constexpr uint8_t USBD_STATE_CONFIGURED = 3;
constexpr uint32_t CDC_DATA_FS_MAX_PACKET_SIZE = 64;
constexpr uint32_t APP_RX_DATA_SIZE = 2048;
constexpr uint32_t APP_TX_DATA_SIZE = 2048;
enum {
	CDC_SEND_ENCAPSULATED_COMMAND, CDC_GET_ENCAPSULATED_RESPONSE,
	CDC_SET_COMM_FEATURE, CDC_GET_COMM_FEATURE, CDC_CLEAR_COMM_FEATURE,
	CDC_SET_LINE_CODING, CDC_GET_LINE_CODING, CDC_SET_CONTROL_LINE_STATE, CDC_SEND_BREAK
};
struct USBD_CDC_HandleTypeDef { uint32_t TxState; uint8_t *TxBuffer; uint32_t TxLength; };
struct USBD_HandleTypeDef { uint8_t dev_state; void *pClassData; };
struct USBD_CDC_ItfTypeDef {
	int8_t (*Init)();
	int8_t (*DeInit)();
	int8_t (*Control)(uint8_t, uint8_t *, uint16_t);
	int8_t (*Receive)(uint8_t *, uint32_t *);
	int8_t (*TransmitCplt)(uint8_t *, uint32_t *, uint8_t);
};
extern "C" USBD_CDC_ItfTypeDef USBD_Interface_fops_FS;
extern USBD_HandleTypeDef hUsbDeviceFS;
extern uint8_t UserRxBufferFS[];
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *device, uint8_t *buffer, uint32_t length);
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *device, uint8_t *buffer);
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *device);
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *device);
extern "C" uint8_t CDC_Transmit_FS(uint8_t *buffer, uint16_t length);
void MX_USB_DEVICE_Init();