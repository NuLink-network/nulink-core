# nulink-core

## Overview  

NuLink network is a decentralized solution for privacy-preserving applications developers to implement best practices and best of breed security and privacy. The NuLink network provides endpoint encryption and cryptographic access control. Sensitive user data can be securely shared from any user platform to cloud or decentralized storage and access to that data is granted automatically by policy in Proxy Re-Encryption or Attribute-Based Encryption. For the data user on the other side, Zero-Knowledge Proof can help them verify the data source. In more advanced privacy-preserving use cases, NuLink uses Fully Homomorphic Encryption to customize enterprise-level data computation services.

## Minimum System Requirements  

* Debian/Ubuntu (Recommended)
* 30GB available storage
* 4GB RAM
* x86 architecture
* **Static IP address**
* **Exposed TCP port 9151, make sure it's not occupied**
* Nodes can be run on cloud infrastructure.

## How to run the nulink worker node  

The NuLink Worker is the node to provide cryptographic service in the NuLink network. It provides Proxy Re-encryption service in the Horus network and it will provide more services such as ABE, IBE, ZKP and FHE in NuLink mainnet. The staker needs running a Worker node to be eligible for token reward. 

There are four steps to run a NuLink Worker:
1. Create Worker Account
2. Install NuLink Worker
3. Configure and Run a Worker node
4. Bond the Worker node with your staking account



## Create Worker Account  

Prepare an ETH type account for the Worker. We suggest creating a Worker account different from the staking account. 

If you already know how to create one and access the keystore file, you can skip this step. Otherwise we recommend you to use Geth to create the Worker account.  Please check [here](https://docs.nulink.org/products/nulink_worker/eth_account) for details.

## Install NuLink Worker  

Start to download and install NuLink Worker.  Install it using Docker (recommended) or install it with local installation. See [here](https://docs.nulink.org/products/nulink_worker/worker_install) for more details. 

## Initialize and Run a Worker Node  

Initialize the configuration and start the Worker Node. If install via docker, need to initialize the configuration and run it in Docker. Otherwise please check  [here](https://docs.nulink.org/products/nulink_worker/worker_running) for more details regarding local running. 

## Bond the Worker node with your staking account  

Don't forget to bond it with your staking account to get reward after successfully running a NuLink Worker node using the NuLink Staking Dapp. 

- Navigate to [NuLink Staking Dapp](https://stake.nulink.org)
- Connect with the Staking account and make sure you have staked tokens in the staking pool
- Enter the Worker address and URI to bond
- Click “Bond Worker”

Refer [here](https://docs.nulink.org/products/staking_dapp) for more usage of NuLink Staking Dapp.


## Support  

You can find more  informations: 
* [**Documentation**](https://docs.nulink.org/)
* [**Website**](https://www.nulink.org/)

If you seek more technical help, please join our [**Community**](https://discord.com/invite/25CQFUuwJS).