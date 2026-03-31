# SS13Lib

A drop in library for [Space Station 13](https://spacestation13.com) servers to integrate, allowing for authentication and discoverability on the SS13 Launcher, via the SS13Hub backend.

## Integration Guide

1. Copy the contents of dmsrc into `ss13lib` in your `code/` directory.
2. Copy ss13lib.dm into a file of the same name, placed anywhere.
3. In your .dme, add ss13lib.dm as *early* as possible and ss13lib.dme as *late* as possible.
4. Carry out the configuration steps per ss13lib.dm, placing any external configuration *before* ss13lib.dm in your .dme.

## TODOs
- Create Topic hook
- Shore up schema for:
	- handshake
	- authentication
	- topic
- Trial integrations into actual codebases
