/*
 * SW3 toggles the RGB LED on/off.
 * SW2 toggles a continuous colour-fade animation.
 * Onboard P3T1755 temperature sensor is read and printed every 2 seconds.
 */

#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/input/input.h>
#include <zephyr/dt-bindings/input/input-event-codes.h>
#include <zephyr/sys/printk.h>

static const struct gpio_dt_spec led_r = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);
static const struct gpio_dt_spec led_g = GPIO_DT_SPEC_GET(DT_ALIAS(led1), gpios);
static const struct gpio_dt_spec led_b = GPIO_DT_SPEC_GET(DT_ALIAS(led2), gpios);

static const struct device *const temp_dev = DEVICE_DT_GET(DT_ALIAS(ambient_temp0));

/* Software PWM driven from a timer ISR: PWM_STEPS ticks of PWM_TICK_US each
 * make up one refresh period. Runs in interrupt context so the main thread
 * is free (sleeping) most of the time and button input stays responsive.
 */
#define PWM_STEPS   32
#define PWM_TICK_US 100

static volatile bool leds_on = true;
static volatile bool fading;
static volatile uint8_t duty_r = PWM_STEPS, duty_g, duty_b;

static void pwm_tick(struct k_timer *timer)
{
	ARG_UNUSED(timer);
	static uint8_t step;

	step = (step + 1) % PWM_STEPS;

	gpio_pin_set_dt(&led_r, leds_on && step < duty_r);
	gpio_pin_set_dt(&led_g, leds_on && step < duty_g);
	gpio_pin_set_dt(&led_b, leds_on && step < duty_b);
}

K_TIMER_DEFINE(pwm_timer, pwm_tick, NULL);

/* Map hue (0..359) onto a 6-segment colour wheel, duty range 0..PWM_STEPS */
static void hue_to_rgb(uint16_t hue, uint8_t *r, uint8_t *g, uint8_t *b)
{
	uint8_t rising = ((hue % 60) * PWM_STEPS) / 60;
	uint8_t falling = PWM_STEPS - rising;

	switch (hue / 60) {
	case 0: *r = PWM_STEPS; *g = rising;    *b = 0;         break;
	case 1: *r = falling;   *g = PWM_STEPS; *b = 0;         break;
	case 2: *r = 0;         *g = PWM_STEPS; *b = rising;    break;
	case 3: *r = 0;         *g = falling;   *b = PWM_STEPS; break;
	case 4: *r = rising;    *g = 0;         *b = PWM_STEPS; break;
	default: *r = PWM_STEPS; *g = 0;        *b = falling;   break;
	}
}

static void input_cb(struct input_event *evt, void *user_data)
{
	ARG_UNUSED(user_data);

	if (evt->value == 0) {
		return; /* react on press only */
	}

	if (evt->code == INPUT_KEY_1) {
		leds_on = !leds_on;
		printk("SW3: LED %s\n", leds_on ? "ON" : "OFF");
	} else if (evt->code == INPUT_KEY_0) {
		fading = !fading;
		printk("SW2: colour fade %s\n", fading ? "started" : "stopped");
	}
}
INPUT_CALLBACK_DEFINE(NULL, input_cb, NULL);

int main(void)
{
	if (!gpio_is_ready_dt(&led_r) || !gpio_is_ready_dt(&led_g) || !gpio_is_ready_dt(&led_b)) {
		printk("LED GPIOs not ready\n");
		return 0;
	}
	gpio_pin_configure_dt(&led_r, GPIO_OUTPUT_INACTIVE);
	gpio_pin_configure_dt(&led_g, GPIO_OUTPUT_INACTIVE);
	gpio_pin_configure_dt(&led_b, GPIO_OUTPUT_INACTIVE);

	bool temp_ready = device_is_ready(temp_dev);

	if (!temp_ready) {
		printk("Temperature sensor not ready\n");
	}

	printk("Ready. SW2 = colour fade, SW3 = LED on/off\n");

	k_timer_start(&pwm_timer, K_USEC(PWM_TICK_US), K_USEC(PWM_TICK_US));

	uint16_t hue = 0;
	int64_t next_temp_report = k_uptime_get();

	while (1) {
		if (fading) {
			uint8_t r, g, b;

			hue = (hue + 2) % 360;
			hue_to_rgb(hue, &r, &g, &b);
			duty_r = r;
			duty_g = g;
			duty_b = b;
		}

		if (temp_ready && k_uptime_get() >= next_temp_report) {
			struct sensor_value temp;

			if (sensor_sample_fetch(temp_dev) == 0 &&
			    sensor_channel_get(temp_dev, SENSOR_CHAN_AMBIENT_TEMP, &temp) == 0) {
				printk("Temperature: %d.%02d C\n", temp.val1,
				       temp.val2 / 10000);
			}
			next_temp_report = k_uptime_get() + 2000;
		}

		k_msleep(20);
	}
	return 0;
}
