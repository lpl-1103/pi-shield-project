#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

int main(void)
{
	printk("llext_min ready. Use 'llext' shell commands to load code.\n");
	return 0;
}
