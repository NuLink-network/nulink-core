### Developing with Docker

The intention of the Docker configurations in this directory is to enable anyone to develop and test NuLink on all major operating systems with minimal prerequisites and installation hassle.

#### quickstart

* install [Docker](https://docs.docker.com/install/)
* install [Docker Compose](https://docs.docker.com/compose/install/)
* cd to deploy/docker (where this README is located)
* `docker-compose up --build` **this must be done once to complete install, and you need run the command as root privilege**

Then you can do things like:

* init an ursula config:

`docker-compose run nulink nulink ursula init --signer keystore://D:\\keystore\\to\path\\keystore --eth-provider https://http-testnet.hecochain.com --network heco_testnet --payment-provider https://http-testnet.hecochain.com --payment-network heco_testnet --operator-address  0x7DEff413E415bd2507da4988393d8540a28bf3c6 --max-gas-price 2000000000000`
* start up an ursula:
  `docker-compose run nulink nulink ursula run --teacher https://8.219.188.70:9151 --no-block-until-ready`
* open a shell:
  `docker-compose run nulink bash`


**tested on (Ubuntu 20, MacOS 10.14, Windows 10)*


## Pycharm (pro version only)
* You can configure pycharm to use the python interpreter inside docker.
* docs for this are [here](https://www.jetbrains.com/help/pycharm/using-docker-compose-as-a-remote-interpreter.html#docker-compose-remote)
