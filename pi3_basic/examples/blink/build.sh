gcc -o blink -I../../src ../../src/bcm2835.c blink.c -D_PI2_
gcc -o relay -I../../src ../../src/bcm2835.c relay.c -D_PI2_
gcc -o pir -I../../src ../../src/bcm2835.c pir.c -D_PI2_
gcc -o buzzer -I../../src ../../src/bcm2835.c buzzer.c -D_PI2_
