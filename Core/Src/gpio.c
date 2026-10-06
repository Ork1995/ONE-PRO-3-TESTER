/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    gpio.c
  * @brief   This file provides code for the configuration
  *          of all used GPIO pins.
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

/* Includes ------------------------------------------------------------------*/
#include "gpio.h"

/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/*----------------------------------------------------------------------------*/
/* Configure GPIO                                                             */
/*----------------------------------------------------------------------------*/
/* USER CODE BEGIN 1 */

/* USER CODE END 1 */

/** Configure pins as
        * Analog
        * Input
        * Output
        * EVENT_OUT
        * EXTI
*/
void MX_GPIO_Init(void)
{

  GPIO_InitTypeDef GPIO_InitStruct = {0};

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOG_CLK_ENABLE();
  HAL_PWREx_EnableVddIO2();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(WM_SIM_1_GPIO_Port, WM_SIM_1_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOE, WM_SIM_2_Pin|V_SNS1_10K_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOD, WM_SIM_3_Pin|WM_SIM_4_Pin|V_SNS1_3K3_Pin|I_SNS3_SEL_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOG, VAI4_VEN_Pin|I_SNS1_SEL_Pin|VSMPL_ONF_Pin|I_SNS2_SEL_Pin
                          |V_SNS3_10K_Pin|I_SNS4_SEL_Pin|V_SNS2_3K3_Pin|V_SNS2_10K_Pin
                          |V_SNS3_3K3_Pin|V_SNS4_3K3_Pin|V_SNS4_10K_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOC, VSEN_ONF_Pin|VAI1_VEN_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOB, VAI3_VEN_Pin|VAI2_VEN_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin : WM_SIM_1_Pin */
  GPIO_InitStruct.Pin = WM_SIM_1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(WM_SIM_1_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pin : WAKE_NINT_Pin */
  GPIO_InitStruct.Pin = WAKE_NINT_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(WAKE_NINT_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pins : WM_SIM_2_Pin V_SNS1_10K_Pin */
  GPIO_InitStruct.Pin = WM_SIM_2_Pin|V_SNS1_10K_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);

  /*Configure GPIO pins : WM_SIM_3_Pin WM_SIM_4_Pin V_SNS1_3K3_Pin I_SNS3_SEL_Pin */
  GPIO_InitStruct.Pin = WM_SIM_3_Pin|WM_SIM_4_Pin|V_SNS1_3K3_Pin|I_SNS3_SEL_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

  /*Configure GPIO pins : VAI4_VEN_Pin I_SNS1_SEL_Pin VSMPL_ONF_Pin I_SNS2_SEL_Pin
                           V_SNS3_10K_Pin I_SNS4_SEL_Pin V_SNS2_3K3_Pin V_SNS2_10K_Pin
                           V_SNS3_3K3_Pin V_SNS4_3K3_Pin V_SNS4_10K_Pin */
  GPIO_InitStruct.Pin = VAI4_VEN_Pin|I_SNS1_SEL_Pin|VSMPL_ONF_Pin|I_SNS2_SEL_Pin
                          |V_SNS3_10K_Pin|I_SNS4_SEL_Pin|V_SNS2_3K3_Pin|V_SNS2_10K_Pin
                          |V_SNS3_3K3_Pin|V_SNS4_3K3_Pin|V_SNS4_10K_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOG, &GPIO_InitStruct);

  /*Configure GPIO pins : VSEN_ONF_Pin VAI1_VEN_Pin */
  GPIO_InitStruct.Pin = VSEN_ONF_Pin|VAI1_VEN_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

  /*Configure GPIO pins : VAI3_VEN_Pin VAI2_VEN_Pin */
  GPIO_InitStruct.Pin = VAI3_VEN_Pin|VAI2_VEN_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* EXTI interrupt init*/
  HAL_NVIC_SetPriority(EXTI0_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(EXTI0_IRQn);

}

/* USER CODE BEGIN 2 */

/* USER CODE END 2 */
