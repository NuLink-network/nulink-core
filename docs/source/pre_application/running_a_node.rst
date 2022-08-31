.. _running-a-node:

==================
Running a PRE Node
==================

.. attention::

    In order to run a PRE node on Threshold, ``nulink`` v6.0.0 or above will be required.
    See `releases <https://pypi.org/project/nulink/#history>`_ for the latest version.


.. note::

    NuLink maintains a separate self-contained CLI that automates the initialization
    and management of PRE nodes deployed on cloud infrastructure. This CLI leverages
    automation tools such as Ansible and Docker to simplify the setup and management
    of nodes running in the cloud (*under active development and currently limited to
    testnet automation*). See :ref:`managing-cloud-nodes`.

After :ref:`staking on Threshold <stake-initialization>`, and finding a server that meets the :ref:`requirements <node-requirements>`, running a PRE node entails the following:

#. :ref:`install-nulink`
#. :ref:`bond-operator`
#. :ref:`configure-and-run-node`
#. :ref:`qualify-node`
#. :ref:`manage-node`


.. _install-nulink:

Install ``nulink``
====================

See ``nulink`` :doc:`installation reference</references/installation>`. There is the option
of using Docker (recommended) or a local installation.


.. _bond-operator:

Bond Operator
=============

The Staking Provider must be bonded to an :ref:`Operator address<operator-address-setup>`. This
should be performed by the Staking Provider via the ``nulink bond`` command (directly or as part of a Docker command). Run
``nulink bond --help`` for usage. The Operator address is the ETH account that will be used when running the Ursula node.


.. attention::

    This command should **only** be executed by the Staking Provider account. This would be the same as the stake owner account
    for self-managed nodes, or the *node-as-a-service* :ref:`provider <node-providers>` for node delegation.


.. important::

    Once the Operator address is bonded, it cannot be changed for 24 hours.

via UI
------

* Navigate to https://to/be/supplied/to/staker/bond
* Connect with the Staking Provider account to execute the bond operation
* Enter the Operator address to bond
* Click *"Bond Operator"*


via Docker
----------

.. code:: bash

    .. code:: bash

    $ docker run -it \
    -v ~/.local/share/nulink:/root/.local/share/nulink \
    -v ~/.ethereum/:/root/.ethereum               \
    nulink/nulink:latest                      \
    nulink bond                                 \
    --signer <ETH KEYSTORE URI>                   \
    --network <NETWORK NAME>                      \
    --eth-provider <L1 PROVIDER URI>              \
    --staking-provider <STAKING PROVIDER ADDRESS> \
    --operator-address <OPERATOR ADDRESS>

    Are you sure you want to bond staking provider 0x... to operator 0x...? [y/N]: y
    Enter ethereum account password (0x...):

    Bonding operator 0x...
    Broadcasting BONDOPERATOR Transaction ...
    TXHASH 0x...

    OK | 0x...
    Block #14114221 | 0x...
     See https://etherscan.io/tx/0x...


Replace the following values with your own:

   * ``<ETH KEYSTORE URI>`` - The local ethereum keystore (e.g. ``keystore:///root/.ethereum/keystore`` for mainnet)
   * ``<NETWORK NAME>`` - The name of the PRE network (mainnet, heco, heco_testnet)
   * ``<L1 PROVIDER URI>`` - The URI of a local or hosted ethereum node (infura/geth, e.g. ``https://infura.io/…``)
   * ``<STAKING PROVIDER ADDRESS>`` - the ethereum address of the staking provider
   * ``<OPERATOR ADDRESS>`` - the address of the operator to bond


via Local Installation
----------------------

.. code:: bash

    (nulink)$ nulink bond --signer <ETH KEYSTORE URI> --network <NETWORK NAME> --eth-provider <L1 PROVIDER URI> --staking-provider <STAKING PROVIDER ADDRESS> --operator-address <OPERATOR ADDRESS>

    Are you sure you want to bond staking provider 0x... to operator 0x...? [y/N]: y
    Enter ethereum account password (0x...):

    Bonding operator 0x...
    Broadcasting BONDOPERATOR Transaction ...
    TXHASH 0x...

    OK | 0x...
    Block #14114221 | 0x...
     See https://etherscan.io/tx/0x...


Replace the following values with your own:

   * ``<ETH KEYSTORE URI>`` - The local ethereum keystore (e.g. ``keystore:///home/<user>/.ethereum/keystore`` for mainnet)
   * ``<NETWORK NAME>`` - The name of the PRE network (mainnet, heco, heco_testnet)
   * ``<L1 PROVIDER URI>`` - The URI of a local or hosted ethereum node (infura/geth, e.g. ``https://infura.io/…``)
   * ``<STAKING PROVIDER ADDRESS>`` - the ethereum address of the staking provider
   * ``<OPERATOR ADDRESS>`` - the address of the operator to bond


.. _configure-and-run-node:

Configure and Run a PRE Node
============================

Node management commands are issued via the ``nulink ursula`` CLI (directly or as part of a Docker command). For more information
on that command you can run ``nulink ursula –help``.

Initializing the PRE node configuration entails:

- Creation of a nulink-specific keystore to store private encryption keys used
  by the node, which will be protected by a user-specified password.

  .. important::

    This is not to be confused with an ethereum keystore - which stores ethereum account private keys.

- Creation of a persistent node configuration file called ``ursula.json``. This file will be written to disk and contains the various runtime configurations for the node.

All PRE node configuration information will be stored in ``/home/user/.local/share/nulink/`` by default.

.. _run-ursula-with-docker:

Run Node via Docker (Recommended)
---------------------------------

This section is specific to :ref:`Docker installations <docker-installation>` of ``nulink``. The Docker commands will ensure that configuration
information in the local ``/home/user/.local/share/nulink/`` is used by the Docker container.

Export Node Environment Variables
+++++++++++++++++++++++++++++++++

These environment variables are used to better simplify the Docker installation process.

.. code:: bash

    # Password used for creation / update of nulink keystore
    $ export NULINK_KEYSTORE_PASSWORD=<YOUR NULINK KEYSTORE PASSWORD>

    # Password used to unlock node eth account
    $ export NULINK_OPERATOR_ETH_PASSWORD=<YOUR OPERATOR ETH ACCOUNT PASSWORD>


Initialize Node Configuration
+++++++++++++++++++++++++++++

This step creates and stores the PRE node configuration, and only needs to be run once.

.. code:: bash

    $ docker run -it --rm  \
    --name ursula        \
    -v ~/.local/share/nulink:/root/.local/share/nulink \
    -v ~/.ethereum/:/root/.ethereum               \
    -p 9151:9151                                  \
    -e NULINK_KEYSTORE_PASSWORD                 \
    nulink/nulink:latest                      \
    nulink ursula init                          \
    --signer <ETH KEYSTORE URI>                   \
    --eth-provider <L1 PROVIDER URI>              \
    --network <L1 NETWORK NAME>                   \
    --payment-provider <L2 PROVIDER URI>          \
    --payment-network <L2 NETWORK NAME>           \
    --operator-address <OPERATOR ADDRESS>         \
    --max-gas-price <GWEI>


Replace the following values with your own:

   * ``<ETH KEYSTORE URI>`` - The local ethereum keystore (e.g. ``keystore:///root/.ethereum/keystore`` for mainnet)

   * ``<L1 PROVIDER URI>`` - The URI of a local or hosted ethereum node (infura/geth, e.g. ``https://infura.io/…``)
   * ``<L1 NETWORK NAME>`` - The name of the PRE network (mainnet, heco, heco_testnet)

   * ``<L2 PROVIDER URI>`` - The URI of a local or hosted level-two node (infura/bor)
   * ``<L2 NETWORK NAME>`` - The name of a payment network (mainnet, heco, heco_testnet)

   * ``<OPERATOR ADDRESS>`` - The local ETH address to be used by the Ursula node (the one that was bonded)

   * ``<GWEI>`` (*Optional*) - The maximum price of gas to spend on any transaction

Launch the Node
+++++++++++++++

This step starts the PRE node.

.. code:: bash

    $ docker run -d --rm \
    --name ursula      \
    -v ~/.local/share/nulink:/root/.local/share/nulink \
    -v ~/.ethereum/:/root/.ethereum   \
    -p 9151:9151                      \
    -e NULINK_KEYSTORE_PASSWORD     \
    -e NULINK_OPERATOR_ETH_PASSWORD \
    nulink/nulink:latest          \
    nulink ursula run

View Node Logs
++++++++++++++

.. code:: bash

    $ docker logs -f ursula


Upgrade the Node To a Newer Version
+++++++++++++++++++++++++++++++++++

.. code:: bash

    # stop docker container
    $ docker stop ursula

    # pull latest docker image
    $ docker pull nulink/nulink:latest

    # start node (same aforementioned run command)
    $ docker run …


Run Node without Docker
-----------------------

Instead of using Docker, PRE nodes can be run using a :ref:`local installation<local-installation>` of ``nulink``.

Run Node via systemd (Alternate)
++++++++++++++++++++++++++++++++

The node can be run as a `systemd <https://en.wikipedia.org/wiki/Systemd>`_ service.


Configure the node
~~~~~~~~~~~~~~~~~~

.. code:: bash

    $(nulink) nulink ursula init      \
    --signer <ETH KEYSTORE URI>           \
    --eth-provider <L1 PROVIDER URI>      \
    --network <L1 NETWORK NAME>           \
    --payment-provider <L2 PROVIDER URI>  \
    --payment-network <L2 NETWORK NAME>   \
    --operator-address <OPERATOR ADDRESS> \
    --max-gas-price <GWEI>


Replace the following values with your own:

   * ``<ETH KEYSTORE URI>`` - The local ethereum keystore (e.g. ``keystore:///home/<user>/.ethereum/keystore`` for mainnet)

   * ``<L1 PROVIDER URI>`` - The URI of a local or hosted ethereum node (infura/geth, e.g. ``https://infura.io/…``)
   * ``<L1 NETWORK NAME>`` - The name of the PRE network (mainnet, heco, heco_testnet)

   * ``<L2 PROVIDER URI>`` - The URI of a local or hosted level-two node (infura/bor)
   * ``<L2 NETWORK NAME>`` - The name of a payment network (mainnet, heco, heco_testnet)

   * ``<OPERATOR ADDRESS>`` - The local ETH address to be used by the Ursula node (the one that was bonded)

   * ``<GWEI>`` (*Optional*) - The maximum price of gas to spend on any transaction


Create Node Service Template
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a file named ``ursula.service`` in ``/etc/systemd/system``, and add this template to it

.. code:: bash

    [Unit]
    Description="Ursula, a PRE Node."

    [Service]
    User=<YOUR USERNAME>
    Type=simple
    Environment="NULINK_OPERATOR_ETH_PASSWORD=<YOUR OPERATOR ADDRESS PASSWORD>"
    Environment="NULINK_KEYSTORE_PASSWORD=<YOUR PASSWORD>"
    ExecStart=<VIRTUALENV PATH>/bin/nulink ursula run

    [Install]
    WantedBy=multi-user.target


Replace the following values with your own:

- ``<YOUR USER>`` - The host system’s username to run the process with (best practice is to use a dedicated user)
- ``<YOUR OPERATOR ADDRESS PASSWORD>`` - Operator’s ETH account password
- ``<YOUR PASSWORD>`` - ``nulink`` keystore password
- ``<VIRTUALENV PATH>`` - The absolute path to the python virtual environment containing the ``nulink`` executable.
  Run ``pipenv –venv`` within the virtual environment to get the virtual environment path.


Enable Node Service
~~~~~~~~~~~~~~~~~~~

.. code:: bash

    $ sudo systemctl enable ursula


Run Node Service
~~~~~~~~~~~~~~~~

.. code:: bash

    $ sudo systemctl start ursula


Check Node Service Status
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    # Application Logs
    $ tail -f ~/.local/share/nulink/nulink.log

    # Systemd status
    $ systemctl status ursula

    # Systemd Logs
    $ journalctl -f -t ursula


Restart Node Service
~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    $ sudo systemctl restart ursula


Run Node Manually
+++++++++++++++++

Configure the Node
~~~~~~~~~~~~~~~~~~

If you’d like to use another own method of running the Node's process in the
background,, here is how to run Ursula using the CLI directly.

First initialize a Node configuration:

.. code:: bash

    $(nulink) nulink ursula init      \
    --signer <ETH KEYSTORE URI>           \
    --eth-provider <L1 PROVIDER URI>      \
    --network <L1 NETWORK NAME>           \
    --payment-provider <L2 PROVIDER URI>  \
    --payment-network <L2 NETWORK NAME>   \
    --operator-address <OPERATOR ADDRESS> \
    --max-gas-price <GWEI>

Replace the following values with your own:

   * ``<ETH KEYSTORE URI>`` - The local ethereum keystore (e.g. ``keystore:///home/<user>/.ethereum/keystore`` for mainnet)

   * ``<L1 PROVIDER URI>`` - The URI of a local or hosted ethereum node (infura/geth, e.g. ``https://infura.io/…``)
   * ``<L1 NETWORK NAME>`` - The name of the PRE network (mainnet, heco, heco_testnet)

   * ``<L2 PROVIDER URI>`` - The URI of a local or hosted level-two node (infura/bor)
   * ``<L2 NETWORK NAME>`` - The name of a payment network (mainnet, heco, heco_testnet)

   * ``<OPERATOR ADDRESS>`` - The local ETH address to be used by the Ursula node (the one that was bonded)

   * ``<GWEI>`` (*Optional*) - The maximum price of gas to spend on any transaction


Run the Node

.. code:: bash

    $ nulink ursula run


.. _qualify-node:

Qualify Node
============

Nodes must be fully qualified: funded with ETH and bonded to an operator address,
in order to fully start. Nodes that are launched before qualification will
pause until they have a balance greater than 0 ETH, and are bonded to an
Operator address. Once both of these requirements are met, the node will
automatically continue startup.

Waiting for qualification:

.. code:: bash

    Defaulting to Ursula configuration file: '/root/.local/share/nulink/ursula.json'
    Authenticating Ursula
    Starting services
    ⓘ  Operator startup is paused. Waiting for bonding and funding ...
    ⓘ  Operator startup is paused. Waiting for bonding and funding ...
    ⓘ  Operator startup is paused. Waiting for bonding and funding …

Continuing startup after funding and bonding:

.. code:: bash

    ...
    ⓘ  Operator startup is paused. Waiting for bonding and funding ...
    ✓ Operator is funded with 0.641160744670608582 ETH
    ✓ Operator 0x2507beC003324d1Ec7F42Cc03B95d213D2E0b238 is bonded to staking provider 0x4F29cC79B52DCc97db059B0E11730F9BE98F1959
    ✓ Operator already confirmed.  Not starting worktracker.
    ...
    ✓ Rest Server https://1.2.3.4:9151
    Working ~ Keep Ursula Online!


.. _manage-node:

Node Management
===============

Update Node Configuration
-------------------------

These configuration settings will be stored in an ursula configuration file, ``ursula.json``, stored
in ``/home/user/.local/share/nulink`` by default.

All node configuration values can be modified using the config command, ``nulink ursula config``

.. code:: bash

    $ nulink ursula config --<OPTION> <NEW VALUE>

    # Usage
    $ nulink ursula config –help

    # Update the max gas price setting
    $ nulink ursula config --max-gas-price <GWEI>

    # Change the Ethereum provider to use
    nulink ursula config --eth-provider <ETH PROVIDER URI>

    # Accept payments for service using the SubscriptionManager contract on heco/heco_testnet
    nulink ursula config --payment-method SubscriptionManager --payment-network heco_testnet

    # View the current configuration
    nulink ursula config

    #
    # Non-default configuration file path
    #

    # View the current configuration of a non-default configuration file path
    nulink ursula config --config-file <CONFIG PATH>

    # Update the max gas price setting of a non-default configuration file path
    nulink ursula config --config-file <CONFIG PATH> --eth-provider <ETH PROVIDER URI>


.. important::

    The node must be restarted for any configuration changes to take effect.


Node Status
-----------

Node Logs
+++++++++

A reliable way to check the status of a node is to view the logs.

* View logs for a Docker-launched Ursula:

  .. code:: bash

      $ docker logs -f ursula

* View logs for a systemd or CLI-launched Ursula:

  .. code:: bash

      # Systemd Logs
      journalctl -f -t ursula

      # Application Logs
      tail -f ~/.local/share/nulink/nulink.log


Node Status Page
++++++++++++++++

Once the node is running, you can view its public status page at ``https://<node_ip>:9151/status``.

.. image:: ../.static/img/Annotated-Ursula-Status-Webpage-v2.svg
    :target: ../.static/img/Annotated-Ursula-Status-Webpage-v2.svg

- *Nickname Icon* - A visual representation of the node's nickname words and colors
- *Staking Provider Nickname* - A nickname/codename for the node derived from the Staking Provider address
- *Staking Provider Address* - The Staking Provider address this node is bonded to
- *Client Version* - The version of nulink this node is running
- *Network Name* - The network this node is running on (mainnet, heco, heco_testnet).
- *Peer Count* - The total number of peers this node has discovered.
- *Fleet State Checksum* - A checksum representing all currently known peers
- *Fleet State Icon* - A visual representation of the fleet state's checksum word and color
- *Fleet State History* - The most recent historical fleet states known by this node, sorted from most recent to oldest
- *Peer Nickname* - The nickname of a peer derived from it's Staking Provider address
- *Peer Fleet State* - The current fleet state of a peer node
- *Peer Staking Provider Address* - The Staking Provider address of a peer
- *Verified Nodes* - The collection of nodes that have been and validated by this node (valid metadata and staking status)
- *Unverified Nodes* - The collection of nodes that have not been contacted or validated by this node
