#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void UsbCdc_Configured(void);
void UsbCdc_Reset(void);
void UsbCdc_Suspend(void);
void UsbCdc_Resume(void);
void UsbCdc_Receive(const uint8_t *buffer, uint32_t length);
void UsbCdc_TransmitComplete(void);
void UsbCdc_StartupFailed(void);

#ifdef __cplusplus
}
#endif