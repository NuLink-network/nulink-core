Environment Variables
=====================

Environment variables are used for configuration in various areas of the codebase to facilitate automation. The
constants for these variables are available in ``nulink.config.constants``.

Where applicable, values are evaluated in the following order of precedence:

#. CLI parameter
#. Environment variable
#. Configuration file
#. Optional default in code


General
-------

* `NULINK_KEYSTORE_PASSWORD`
    Password for the `nulink` Keystore.
* `NULINK_ETH_PROVIDER_URI`
    Default Web3 node provider URI.
* `NULINK_STAKING_PROVIDERS_PAGINATION_SIZE`
    Default pagination size for the maximum number of active staking providers to retrieve from PREApplication in
    one contract call.
* `NULINK_STAKING_PROVIDERS_PAGINATION_SIZE_LIGHT_NODE`
    Default pagination size for the maximum number of active staking providers to retrieve from PREApplication in
    one contract call when a light node provider is being used.
* `NULINK_STAKING_PROVIDER_ETH_PASSWORD`
    Password for a staking provider's Keystore.

Alice
-----

* `NULINK_ALICE_ETH_PASSWORD`
    Password for Ethereum account used by Alice.


Bob
----

* `NULINK_BOB_ETH_PASSWORD`
    Password for Ethereum account used by Bob.


Ursula (Operator)
-----------------

* `NULINK_OPERATOR_ADDRESS`
    Ethereum account used by Ursula.
* `NULINK_OPERATOR_ETH_PASSWORD`
    Password for Ethereum account used by Ursula (Operator).
