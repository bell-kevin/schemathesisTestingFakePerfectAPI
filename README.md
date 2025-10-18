<a name="readme-top"></a>

#

## What's this API all about?

Imagine you have a friendly robot that loves to play with words. This API is like a set of buttons you can press to ask the robot for help:

* **"How are you doing?" check** – When you visit `/status`, the robot simply says everything is "ok" so you know the service is awake.
* **Message repeater** – When you send a message to `/echo`, the robot repeats it back to you. You can ask it to shout (UPPERCASE) or say the message a few times in a row, up to five. It also tells you how long the final message is.
* **Word mirror** – When you use `/inspect`, the robot looks at your message, spells it backwards like a mirror, counts how many characters it has, and tells you whether the message reads the same forwards and backwards (that's called a palindrome!). You can even tell it to ignore upper- vs lower-case letters when it checks.

So, the API is basically a tidy word helper that always answers in the same predictable way, which makes it great for practicing and testing.

## Running the Fake Perfect API

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the development server:
   ```bash
   uvicorn perfectapi.app:app --reload
   ```
3. Visit http://localhost:8000/docs to explore the automatically generated OpenAPI documentation.

The repository also contains a static `openapi.yaml` document that mirrors the FastAPI-generated schema. It can be used directly with Schemathesis:

```bash
schemathesis run openapi.yaml --base-url=http://localhost:8000
```

### Running Schemathesis against the Render deployment

Render's free instances hibernate when idle and can take up to a minute to resume.  Schemathesis applies a 10 second read timeout while downloading the OpenAPI document, so attempts to load `https://fake-perfect-api.onrender.com/openapi.yaml` directly frequently fail on a cold start.  Use the warm-up helper shipped with this repository to wait for the service and then execute Schemathesis with the local schema file:

```bash
python -m perfectapi.warmup -- --checks=all
```

Cloudflare sits in front of Render and strips the `Allow` header from `TRACE` requests before they reach the application.  To avoid spurious failures from Schemathesis' `unsupported_method` check the warm-up helper automatically adds `--exclude-checks unsupported_method` unless you supply your own `--checks` / `--exclude-checks` arguments.  If you prefer to invoke Schemathesis manually, include the same flag in your command line.

The script accepts additional Schemathesis flags after the `--` separator and defaults the base URL to the production deployment.  Use `python -m perfectapi.warmup --help` for all available options (timeouts, base URL overrides, etc.).

## Deploying on Render (managed free tier)

The repository includes a [Render Blueprint](render.yaml) so you can deploy the API on Render's free web service tier:

1. Create a new Render account (or log in) and click **New → Blueprint Deploy**.
2. Point Render at this repository URL and select the `render.yaml` file when prompted.
3. Accept the defaults in the generated service (plan: **Free**, runtime: **Python 3.11**).
4. Click **Deploy**. Render will install the dependencies via `pip install -r requirements.txt` and start Uvicorn with `perfectapi.app:app`.
5. Once the deploy finishes, your API will be available at the HTTPS URL Render assigns (check the **Logs** tab if you need to troubleshoot).

The blueprint listens on the port provided by Render and exposes the OpenAPI docs at `/docs`, which Render also uses for its health check.

--------------------------------------------------------------------------------------------------------------------------
== We're Using GitHub Under Protest ==

This project is currently hosted on GitHub.  This is not ideal; GitHub is a
proprietary, trade-secret system that is not Free and Open Souce Software
(FOSS).  We are deeply concerned about using a proprietary system like GitHub
to develop our FOSS project. I have a [website](https://bellKevin.me) where the
project contributors are actively discussing how we can move away from GitHub
in the long term.  We urge you to read about the [Give up GitHub](https://GiveUpGitHub.org) campaign 
from [the Software Freedom Conservancy](https://sfconservancy.org) to understand some of the reasons why GitHub is not 
a good place to host FOSS projects.

If you are a contributor who personally has already quit using GitHub, please
email me at **bellKevin@pm.me** for how to send us contributions without
using GitHub directly.

Any use of this project's code by GitHub Copilot, past or present, is done
without our permission.  We do not consent to GitHub's use of this project's
code in Copilot.

![Logo of the GiveUpGitHub campaign](https://sfconservancy.org/img/GiveUpGitHub.png)

<p align="right"><a href="#readme-top">back to top</a></p>
