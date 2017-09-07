Fast FTP deploy
===============

Installation
------------

1. Python 2.7 required
2. Download/compile/install hashdeep binaries, tigerdeep binary must be in PATH (https://github.com/jessek/hashdeep)
3. Install python dependencies ``pip install -r requirements.txt``
4. Obtain sources ``git clone https://bitbucket.org/kolinger/ftp-deploy.git``

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
    ]
}
````

Usage
-----

``python deploy.py /path/to/my/configuration.json``

Create local configuration file named .ftp-deploy.json and run just  
``python deploy.py``

Upgrade
-------

Just ```git pull```


Make binary/package
-------------------

``pip install pyinstaller``  
``pyinstaller --onefile deploy.py``


TODO
----

1. Better error handling
    1. Count failed and successful uploads and show result at the end
    2. Try re-upload failed objects (enabled/disabled/retry count configured via .json)
2. Performance improvements - threads, threads, threads for everyone
    1. Multi-threaded scanning
    2. Multi-threaded deletion
    3. Multi-threaded purge
3. More friendly installation/usage
    1. Virtualenv?
    2. Some kind of binary like package with no/minimal external dependencies?

Bugs
----

1. Minority of objects is randomly omitted
    1. Fix: implement better error handling
    2. Workaround: run deploy multiple time until no object is found
