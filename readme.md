Fast FTP deploy
===============

Installation
------------

1. Python 2.7 required
2. Obtain sources ``git clone https://bitbucket.org/kolinger/ftp-deploy.git``
3. Done

Configuration
-------------

Configuration is done via .json files.

````
{
    "local": "/local/path",
    "connection": {
        "threads": 10,
        "secure": false,
        "host": "hostname",
        "port": 21,
        "user": "username",
        "password": "password",
        "root": "/remote/path"
    },
    "retry_count": 10,
    "ignore": [
        ".git",
        ".idea",
        "/app/config/config.local.neon",
        "/app/temp/",
        "/app/log/",
        "/assets/manager/dist",
        "/assets/client/dist",
        "/files/",
        "tests",
        "Tests",
        "examples",
        "Examples",
        "docs"
    ],
    "purge": [
        "/app/temp/cache",
        "/app/log",
        "/assets/manager/dist",
        "/assets/client/dist"
    ],
    "composer": "/app/composer.json",
    "before": [
        "command1",
        "command2
    ],
    "after": [
        "cleanup-command"
    ]
}
````

When composer file is specified then only production dependencies are deployed (--no-dev). 
Also --prefer-dist is used to exclude unnecessary files.

Usage
-----

``python deploy.py /path/to/my/configuration.json``

or use more user-friendly pattern

``python deploy.py dev``

will look for .ftp-dev.json

or create local configuration file named .ftp-deploy.json and run just  

``python deploy.py``

Before and after command can be skipped with `skip` option.

Upgrade
-------

Just ```git pull```
