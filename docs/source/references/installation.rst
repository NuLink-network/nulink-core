Installation Reference
======================

``nulink`` can be run either from a docker container or via local installation. Running ``nulink``
via a docker container simplifies the installation process and negates the need for a local installation.


.. _docker-installation:

Docker Installation and Update
------------------------------

#. Install `Docker <https://docs.docker.com/install/>`_
#. *Optional* Depending on the setup you want, post install instructions, additional
   docker configuration is available `here <https://docs.docker.com/engine/install/linux-postinstall/>`_.
#. Get the latest nulink image:

.. code:: bash

    docker pull nulink/nulink:latest

.. _local-installation:

Local Installation
------------------

``nulink`` supports Python 3.7 and 3.8. If you don’t already have it, install `Python <https://www.python.org/downloads/>`_.

In order to isolate global system dependencies from nulink-specific dependencies, we *highly* recommend
using ``python-virtualenv`` to install ``nulink`` inside a dedicated virtual environment.

For full documentation on virtualenv see: https://virtualenv.pypa.io/en/latest/:

#. Create a Virtual Environment

   Create a virtual environment in a folder somewhere on your machine.This virtual
   environment is a self-contained directory tree that will contain a python
   installation for a particular version of Python, and various installed packages needed to run the node.

   .. code-block:: bash

       $ python -m venv /your/path/nulink-venv
       ...


#. Activate the newly created virtual environment:

   .. code-block:: bash

       $ source /your/path/nulink-venv/bin/activate
       ...
       (nulink-venv)$


   A successfully activated virtual environment is indicated by ``(nulink-venv)$`` prepended to your console's prompt

   .. note::

       From now on, if you need to execute any ``nulink`` commands you should do so within the activated virtual environment.


#. Install/Update the ``nulink`` package

   .. code-block:: bash

       (nulink-venv)$ pip3 install -U nulink


#. Verify Installation

    Before continuing, verify that your ``nulink`` installation and entry points are functional.

    Activate your virtual environment, if not activated already:

    .. code-block:: bash

       $ source /your/path/nulink-venv/bin/activate

    Next, verify ``nulink`` is importable.  No response is successful, silence is golden:

    .. code-block:: bash

       (nulink-venv)$ python -c "import nulink"

    Then, run the ``nulink --help`` command:

    .. code-block:: bash

       (nulink-venv)$ nulink --help
       ...

    If successful you will see a list of possible usage options (\ ``--version``\ , ``--config-path``\ , ``--logging-path``\ , etc.) and
    commands (\ ``status``\ , ``ursula``\ , etc.).
