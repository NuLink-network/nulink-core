### Build to generate tag
```shell
docker-compose build
```

output:
```shell
    Successfully built d8dd7bcb2375
    Successfully tagged nulink:latest
```
```shell
docker-compose ps or docker images
```

output:
```shell
    Name     Command    State    Ports
    -----------------------------------
    nulink   /bin/bash   Exit 0
```

```shell
docker login

docker tag nulink:latest nulink/nulink:latest

docker push nulink/nulink:latest
```

### how to run

```shell
docker pull nulink/nulink:latest

docker run  -p 127.0.0.1:19123:19123/tcp -v /path/host/Machine/directory:/code --rm -it nulink/nulink /bin/bash
```