FROM nucypher/rust-python:3.9.9
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /code

RUN export PATH="$HOME/.local/bin:$PATH"

# Update
RUN apt-get update -y && apt-get upgrade -y && apt-get install patch gcc libffi-dev wget git -y

# make an install directory
RUN mkdir /install
WORKDIR /install

# copy only the exact files needed for install into the container
COPY ./nulink/__about__.py /install/nulink/
COPY README.md /install
COPY setup.py /install
#COPY ./nulink/blockchain/eth/sol/__conf__.py /install/nulink/blockchain/eth/sol/__conf__.py
#COPY scripts/installation/install_solc.py /install/scripts/installation/
COPY dev-requirements.txt /install
COPY requirements.txt /install
COPY docs-requirements.txt /install
COPY dev/docker/scripts/install/entrypoint.sh /install

# install reqs and solc
RUN pip install --upgrade pip
RUN pip3 install .[dev] --src /usr/local/src
RUN pip3 install ipdb


RUN python3 /install/setup.py develop

# now install solc
# RUN python3 /install/scripts/installation/install_solc.py


# https://stackoverflow.com/questions/26504846/copy-directory-to-another-directory-using-add-command
COPY ./site-packages-cover/web3_6.0.0b1 /code/site-packages-cover/
#RUN ls /code/site-packages-cover/
# Replace the files that modify the source code
RUN sh -c 'python3 -m site --user-site  | xargs sudo chmod 755'
RUN sh -c 'python3 -m site --user-site  | xargs -I{} sudo cp -rf /code/site-packages-cover/** "{}"'

# this gets called after volumes are mounted and so can modify the local disk
CMD ["/install/entrypoint.sh"]
