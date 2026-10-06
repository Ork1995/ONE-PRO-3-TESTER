/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32l4xx_hal.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
#define WM_SIM_1_Pin GPIO_PIN_8
#define WM_SIM_1_GPIO_Port GPIOF
#define SENS3_INP_ADC_Pin GPIO_PIN_2
#define SENS3_INP_ADC_GPIO_Port GPIOC
#define SENS4_INP_ADC_Pin GPIO_PIN_3
#define SENS4_INP_ADC_GPIO_Port GPIOC
#define WAKE_NINT_Pin GPIO_PIN_0
#define WAKE_NINT_GPIO_Port GPIOA
#define WAKE_NINT_EXTI_IRQn EXTI0_IRQn
#define SENS2_INP_ADC_Pin GPIO_PIN_1
#define SENS2_INP_ADC_GPIO_Port GPIOA
#define SENS1_INP_ADC_Pin GPIO_PIN_5
#define SENS1_INP_ADC_GPIO_Port GPIOA
#define WM_SIM_2_Pin GPIO_PIN_15
#define WM_SIM_2_GPIO_Port GPIOE
#define WM_SIM_3_Pin GPIO_PIN_11
#define WM_SIM_3_GPIO_Port GPIOD
#define WM_SIM_4_Pin GPIO_PIN_12
#define WM_SIM_4_GPIO_Port GPIOD
#define VAI4_VEN_Pin GPIO_PIN_2
#define VAI4_VEN_GPIO_Port GPIOG
#define I_SNS1_SEL_Pin GPIO_PIN_3
#define I_SNS1_SEL_GPIO_Port GPIOG
#define VSMPL_ONF_Pin GPIO_PIN_4
#define VSMPL_ONF_GPIO_Port GPIOG
#define I_SNS2_SEL_Pin GPIO_PIN_5
#define I_SNS2_SEL_GPIO_Port GPIOG
#define V_SNS3_10K_Pin GPIO_PIN_7
#define V_SNS3_10K_GPIO_Port GPIOG
#define VSEN_ONF_Pin GPIO_PIN_6
#define VSEN_ONF_GPIO_Port GPIOC
#define VAI1_VEN_Pin GPIO_PIN_7
#define VAI1_VEN_GPIO_Port GPIOC
#define VSEN_PWM_Pin GPIO_PIN_9
#define VSEN_PWM_GPIO_Port GPIOC
#define JTMS_SWDIO_Pin GPIO_PIN_13
#define JTMS_SWDIO_GPIO_Port GPIOA
#define V_SNS1_3K3_Pin GPIO_PIN_0
#define V_SNS1_3K3_GPIO_Port GPIOD
#define UART2_TX_Pin GPIO_PIN_5
#define UART2_TX_GPIO_Port GPIOD
#define UART2_RX_Pin GPIO_PIN_6
#define UART2_RX_GPIO_Port GPIOD
#define I_SNS3_SEL_Pin GPIO_PIN_7
#define I_SNS3_SEL_GPIO_Port GPIOD
#define I_SNS4_SEL_Pin GPIO_PIN_9
#define I_SNS4_SEL_GPIO_Port GPIOG
#define V_SNS2_3K3_Pin GPIO_PIN_10
#define V_SNS2_3K3_GPIO_Port GPIOG
#define V_SNS2_10K_Pin GPIO_PIN_12
#define V_SNS2_10K_GPIO_Port GPIOG
#define V_SNS3_3K3_Pin GPIO_PIN_13
#define V_SNS3_3K3_GPIO_Port GPIOG
#define V_SNS4_3K3_Pin GPIO_PIN_14
#define V_SNS4_3K3_GPIO_Port GPIOG
#define V_SNS4_10K_Pin GPIO_PIN_15
#define V_SNS4_10K_GPIO_Port GPIOG
#define JTDO_TRACESWO_Pin GPIO_PIN_3
#define JTDO_TRACESWO_GPIO_Port GPIOB
#define NJTRST_Pin GPIO_PIN_4
#define NJTRST_GPIO_Port GPIOB
#define VAI3_VEN_Pin GPIO_PIN_8
#define VAI3_VEN_GPIO_Port GPIOB
#define VAI2_VEN_Pin GPIO_PIN_9
#define VAI2_VEN_GPIO_Port GPIOB
#define V_SNS1_10K_Pin GPIO_PIN_1
#define V_SNS1_10K_GPIO_Port GPIOE

/* USER CODE BEGIN Private defines */

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
