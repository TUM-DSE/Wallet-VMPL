# Note for Wallet measurements

When running an empty `python` runtime, we have for each `Trustlet`:
- `37755` pages for CoW (=`147 MB`)
- `15` owned pages (=`0.059 MB`)
- Important: this number is the same for each new Trustlet.
So each new `Trustlet` increases the memory consumption by `15` pages.
(source: @Sabanic-P)

We calculate the memory consuption using the following formula:
```
memory_consumption = (37755 * 4096) + (#number_of_trustlets * 15 * 4096)
```