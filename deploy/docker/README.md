
#### Test hardware environment requirements

* Debian/Ubuntu (recommended)

* 20GB storage space

* 4 gb of memory

* X86 architecture

* Static IP Address

* Exposed TCP port 9151

#### how to run PRE workers

* install [Docker](https://docs.docker.com/install/)

Then you can do things like:

* docker pull iandy2233/nulink:latest


* docker run -it nulink:latest /bin/bash


* init an ursula config:
  `nulink ursula init --signer keystore://D:\\keystore\\to\path\\keystore --eth-provider https://http-testnet.hecochain.com --network heco_testnet --payment-provider https://http-testnet.hecochain.com --payment-network heco_testnet --operator-address  0x7DEff413E415bd2507da4988393d8540a28bf3c6 --max-gas-price 2000`


* start up an ursula:
  `nulink nulink ursula run --teacher https://IP_ADDRESS:9151 --no-block-until-ready`
