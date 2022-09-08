FROM nucypher/rust-python:3.9.9

ENV PATH=/home/circleci/.local/bin:${PATH}

WORKDIR /code
COPY . /code

RUN pip3 install .[ursula]

# COPY ./deploy/docker/startup.sh .
# copy the third packages modify to code dir
# https://stackoverflow.com/questions/26504846/copy-directory-to-another-directory-using-add-command
COPY ./site-packages-cover/web3_6.0.0b1 /code/site-packages-cover/
#RUN ls /code/site-packages-cover/

# Replace the files that modify the source code
RUN sh -c 'python3 -m site --user-site  | xargs sudo chmod 755 && python3 -m site --user-site  | xargs -I{} sudo cp -rf /code/site-packages-cover/** "{}" '

#RUN sudo sh -c 'echo "${PATH}" >> ~/.bashrc'

#RUN sh -c 'sudo chmod 755 /etc/environment'
#RUN sudo sh -c 'export PATH="$HOME/.local/bin:$PATH" > /etc/environment'

#RUN export PATH="$HOME/.local/bin:$PATH"

#RUN sh -c 'sudo chmod 755 /etc/profile'
#RUN sudo sh -c 'echo export PATH="$HOME/.local/bin:$PATH" >> /etc/profile'

# https://www.baeldung.com/linux/docker-cmd-multiple-commands
#CMD ["/bin/bash","-c","sudo chmod 755 ./startup.sh;./startup.sh"]

RUN export PATH="$HOME/.local/bin:$PATH"

CMD ["/bin/bash"]
