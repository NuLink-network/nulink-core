### Build to generate tag
docker-compose build


```
output:

    Successfully built d8dd7bcb2375
    Successfully tagged nulink:latest
```

docker-compose ps

```
output:

    Name     Command    State    Ports
    -----------------------------------
    nulink   /bin/bash   Exit 0
```

docker login

docker tag nulink:latest iandy2233/nulink:latest

docker push iandy2233/nulink:latest

### how to run

docker pull iandy2233/nulink:latest
docker run  -p 127.0.0.1:19123:19123/tcp -it nulink:latest /bin/bash