# Go-style Chan for Python

Implements Go's chan type in Python as `Chan`.  Can `put`/`get`:

```Python
def babble(ch, what):
    i = 0
    while True:
        ch.put(what + str(i))
        i += 1
        time.sleep(1)

def listen(ch):
    while True:
        print "Heard:", ch.get()

c = Chan()
quickthread(babble, c, "hello")
quickthread(listen, c)
time.sleep(4)
```

Can use `closed` and iteration:

```Python
def sayall(ch, what):
    for thing in what:
        ch.put(thing)
        time.sleep(1)
    ch.close()

def hearall(ch):
    for thing in ch:
        print thing

c = Chan()
quickthread(sayall, c, ['get', 'off', 'my', 'lawn'])
quickthread(hearall, c)
time.sleep(5)
```

And you can wait on multiple channels with `chanselect`:

```Python
def fan_in(outchan, input1, input2):
	while True:
		chan, value = chanselect([input1, input2], [])
		if chan == input1:
		    outchan.put("From 1: " + str(value))
		else:
		    outchan.put("From 2 " + str(value))
```

[![Bitdeli Badge](https://d2weczhvl823v0.cloudfront.net/stuglaser/pychan/trend.png)](https://bitdeli.com/free "Bitdeli Badge")
