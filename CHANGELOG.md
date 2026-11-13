# Changelog

## 0.1.0 (2026-11-13)


### Features

* add issuer onboardings ([d053103](https://github.com/flashpi1/flashpi-python/commit/d053103a06360c91c0ed21f6a9beec751d5bd3ac))
* add issuers with their establishments, emission points and certificates ([82a94d2](https://github.com/flashpi1/flashpi-python/commit/82a94d2b2d257b4ec3c121023426623d8bdc1e4f))
* add pagination to list operations ([470f23f](https://github.com/flashpi1/flashpi-python/commit/470f23f0706024dadf3def628558d5a2f26ae08b))
* add the error classes ([79e3073](https://github.com/flashpi1/flashpi-python/commit/79e3073e358a7d6e5bad0925c7b326b39426e0af))
* add the Flashpi and AsyncFlashpi clients with safe retries ([2b51b92](https://github.com/flashpi1/flashpi-python/commit/2b51b92282a7df08b4f2d69fd17ff6a9a2b1b28c))
* add the package skeleton with its version and typing marker ([dd5460c](https://github.com/flashpi1/flashpi-python/commit/dd5460cca9a19420830485c62ef24c858f8d638f))
* add the status and events resources ([9c22f49](https://github.com/flashpi1/flashpi-python/commit/9c22f496dcf8e348a9ec5e053f41d4d076e6bc85))
* add webhook endpoints and their deliveries ([4cf8635](https://github.com/flashpi1/flashpi-python/commit/4cf86351fadf1e68442bafd243926ab0a9e15ed9))
* issue documents and read them back ([0874000](https://github.com/flashpi1/flashpi-python/commit/0874000d922f00a0ad05b5b55f27c7c7d0950fc9))
* the Python SDK ([e1f2983](https://github.com/flashpi1/flashpi-python/commit/e1f29836e01cb79ac53219b0fcda5c6dd0d6ef0c))
* **types:** add the public types module ([d73c59d](https://github.com/flashpi1/flashpi-python/commit/d73c59d65dd2076d92ae8e010de9c6d2e2502235))
* **types:** generate TypedDicts from the API's OpenAPI document ([60f6787](https://github.com/flashpi1/flashpi-python/commit/60f6787172846479774ab4df734bca4178540874))
* verify webhook signatures ([0aa315f](https://github.com/flashpi1/flashpi-python/commit/0aa315f18deecfbaa391f4d1c40f287ee58e786b))


### Bug fixes

* check header names and values before sending anything ([e197f98](https://github.com/flashpi1/flashpi-python/commit/e197f9818491d9536799d2c8c9cc143fe70b1b3c))
* check the deadline once the answer is read, also after response hooks ([5a0d475](https://github.com/flashpi1/flashpi-python/commit/5a0d47575ef816bbbc334784662309f14850ae2e))
* do not retry a request httpx refuses, nor show why ([cf7d38d](https://github.com/flashpi1/flashpi-python/commit/cf7d38d7f213a78953827bfbc2e565ba02aeaf3f))
* give each attempt one deadline that covers reading the answer ([48cfd71](https://github.com/flashpi1/flashpi-python/commit/48cfd71cbafb8fef57f1d9841864d3b4471d6c3b))
* keep a certificate and its password out of the multipart repr ([cc34bcf](https://github.com/flashpi1/flashpi-python/commit/cc34bcf1d4a2ae4ed864fb464a2787707ae82231))
* keep httpx's own limits when its internals are not there ([eed5ea8](https://github.com/flashpi1/flashpi-python/commit/eed5ea888cbd09589f9e1cf56c2debe9218b9955))
* keep the .p12 and its password out of the frames of an upload error ([9ac950f](https://github.com/flashpi1/flashpi-python/commit/9ac950f3ca913b87d51b5d9e8cc53ed2c8a98536))
* keep the API key out of the frames of request and settings errors ([b7c90ae](https://github.com/flashpi1/flashpi-python/commit/b7c90ae3253544a3968943c1464084684f411da8))
* keep the webhook signing key out of the frames of a verification error ([de4d6f8](https://github.com/flashpi1/flashpi-python/commit/de4d6f8b4fee9bf95db3798b6117c3a33382a7df))
* limit every network operation of a Flashpi attempt to its time left ([3b868b5](https://github.com/flashpi1/flashpi-python/commit/3b868b5d5a46b2d517ecd6966d0e80731b9215b9))
* read a certificate file only up to one byte past the limit ([5254a47](https://github.com/flashpi1/flashpi-python/commit/5254a47905acacc8b2460a3367f44fa7094a27af))
* refuse a body that is not text or bytes before the webhook-id check ([91591dc](https://github.com/flashpi1/flashpi-python/commit/91591dc9232a08bb2cda82e2f4631c104afbcd25))
* refuse a Content-Length or Transfer-Encoding header ([e4bc63e](https://github.com/flashpi1/flashpi-python/commit/e4bc63e08221e4e4e85758e8f20de14c35bc357a))
* refuse a malformed base_url with a FlashpiError ([ebce4f0](https://github.com/flashpi1/flashpi-python/commit/ebce4f018621212e74743ee660519b927c288e32))
* refuse a non-blocking certificate stream that has no data ready ([f57f518](https://github.com/flashpi1/flashpi-python/commit/f57f51867505d6ee069e586134e8ca43199ba9ef))
* refuse an API key with spaces or control characters ([8c51ee5](https://github.com/flashpi1/flashpi-python/commit/8c51ee5ffbfecf9d4c55ef7816fb88b22bdbbc7b))
* refuse header values that are not text on every httpx version ([04f6fb6](https://github.com/flashpi1/flashpi-python/commit/04f6fb6c7d22bc826433fd62f3bf149f011d116f))
* reject a webhook-id that is not UTF-8 as an unmatched signature ([1a0b3dd](https://github.com/flashpi1/flashpi-python/commit/1a0b3ddc86fb5d5ae52f11740742282e9a84b70c))
* **scripts:** refuse a redirect to plain HTTP when syncing the contract ([65a4cca](https://github.com/flashpi1/flashpi-python/commit/65a4cca1e0cf4512bb00d884623a1a285569e17b))
* send header values outside ASCII as UTF-8 on every request ([5bdf182](https://github.com/flashpi1/flashpi-python/commit/5bdf18227fb57f5a033858fd984056090b136813))
* trim a byte order mark around the API key, as Node does ([559a278](https://github.com/flashpi1/flashpi-python/commit/559a2783a271fc49fd3ff956f3afd8f61afd8f8f))
* **types:** type async with_response methods as coroutines ([5975f2c](https://github.com/flashpi1/flashpi-python/commit/5975f2c06821265d979b16a1babb75e50268244c))
