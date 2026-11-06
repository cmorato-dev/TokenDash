# Using the dashboard

**English** · [Español](es/USO.md)

## First sign-in

Open TokenDash in the browser, at `http://COMPUTER-IP:8000`, and sign in with:

- **Username:** `admin`
- **Password:** `tokendash`

Before letting you go on, TokenDash asks for a new password. The initial one is public, because it is published on GitHub, so until you change it you cannot use anything else.

1. In "Old password" type `tokendash`.
2. Type the new password twice.
3. Press **Save the password**.

The new password needs at least 8 characters, cannot be only numbers or a very common password, and cannot be `tokendash` again.

The initial user is only created on a new installation, when there are no users yet. If there is one already, it is not created.

## Language

TokenDash is in English and Spanish. It opens in your browser's language, and you switch it with the **EN · ES** buttons at the top right: the same page opens in the other language and TokenDash remembers your choice. Every page has its address in each language, for example `/en/` and `/es/` for the dashboard.

## Users and passwords

Everything is done from **Administration → Users** (the "Administration" link at the top right).

| I want to… | How |
|---|---|
| Change my password | **Password** link, at the top right |
| Change my username | Administration → Users → click your user → change "Username" → **Save** |
| Create another user | Administration → Users → **Add user** → name and password → **Save** |
| Change another user's password | Administration → Users → click the user → **Reset password** button |
| Delete a user | Administration → Users → click the user → **Delete** |

When you create a user, choose what they can do by ticking the boxes on their page:

| Kind | Boxes ticked | What they can do |
|---|---|---|
| View only | none | See the dashboard and the chart |
| Manager | "Staff status" | Also press "Refresh now" and open the administration |
| Administrator | "Staff status" and "Superuser status" | Everything: connect accounts, manage users and Home Assistant keys |

Make sure there is always at least one administrator.

## Connect ChatGPT

You need a ChatGPT account with Codex, for example Plus or Pro. TokenDash shows the Codex limits, which are the only ones OpenAI publishes as a percentage.

1. Open **Connect accounts** (top right) and press **Sign in with ChatGPT**.
2. OpenAI's official page opens in another tab. Sign in with your account and authorise.
3. When it finishes, that tab shows **"This site can't be reached"**, at an address that starts with `http://localhost:1455/auth/callback?…`. **That is expected:** the code TokenDash needs is inside that address.
4. Copy the full address from the browser's address bar.
5. Go back to the TokenDash tab, paste it into the box that has appeared and press **Complete connection**. Do it within a few minutes, because the code expires.

TokenDash stores the connection encrypted and renews it on its own. Your OpenAI password never goes through TokenDash. To remove it, press **Disconnect**.

## Connect Claude

Claude is linked once, from the console of the computer where TokenDash runs. The dashboard gives you the commands, each with a copy button.

- Follow the steps in **Connect accounts → 2 · Claude**.
- The same guide, in more detail, is in [Link Claude](LINK_CLAUDE.md).

## If you only use ChatGPT or only Claude

By default the dashboard shows both accounts. If you only pay for one subscription:

1. Open **Administration → Settings**.
2. In **Accounts you use**, choose **Only ChatGPT** or **Only Claude**.
3. Press **Save**.

The dashboard then shows a single full-width card, with the 5-hour limit on the left and the weekly one on the right. The chart and "Connect accounts" only show that account, and the server stops reading the other one. If you subscribe to the other one later, go back to **ChatGPT and Claude**. The history of the hidden account is not deleted.

## How often it refreshes

TokenDash reads the limits every 20 minutes. To change it:

1. Open **Administration → Settings**.
2. Choose the frequency, from every 15 minutes to every 6 hours.
3. Press **Save**.

The change applies from the next minute, without restarting anything. The same page says when the last automatic reading was and when the next one is due.

Choose a lower frequency if looking now and then is enough. There is no option under 15 minutes, so the accounts are not queried too often.

## Reading the dashboard

Each card shows one provider:

- **The circle:** the share of the main limit, the 5-hour one, that is still **available**. Below it are the amount used and when it renews.
- **The sentences below:** the other limits, such as the weekly one, each with a bar of what is used. For example: "You have used 26% of the limit this week. It renews on Oct 27 at 07:41."
- **The colour:**
  - Up to half of the limit, the provider's colour: green for ChatGPT and orange for Claude.
  - Past **50 %**, yellow, and the card says "You are past half of the limit".
  - Past **80 %**, red: "Little left".
  - At **100 %**, red: "Out of tokens". Wait until the limit renews.

  The circle follows the main limit and each bar its own. A limit that has already renewed is dimmed and has no warning colour.
- **The label at the top right:**
  - **Updated:** the last reading went well.
  - **Session expired:** the account has to be connected again.
  - **A quota of this account could not be read…:** the server could not read the limit.

  In every case you see the last good data with its date.
- **"It has already renewed":** the limit restarted after the last reading. The number is the last known one, not the current one. It is updated at the next reading.
- **Refresh now:** asks for a reading right away. Wait a minute between presses.

TokenDash reads the limits as often as set in **Settings**, every 20 minutes by default. An open dashboard refreshes itself.

### The chart

"Limits over time" shows the recorded percentage used by each quota. The 24-hour, 7-day and 30-day views retain every reading at its actual time, including intraday peaks and drops.

- **Colours:** each provider and each limit has its colour.
- **Lines:** every quota uses a solid line, with small filled markers. Colours and the legend distinguish the 5-hour and weekly limits.
- **Period:** choose it at the top right, from 24 hours to 5 years.
- **Time axis:** day separators and hour marks show when usage changes. Choose 24 hours for a closer look.
- **Grouping:** 3 and 6 months show weekly averages, 1 year monthly averages, and 5 years yearly averages.
- **Detail:** hover over a point to see its value and date; detailed views also show the time.

Limits restart, so it is normal for the line to go up and down. Detailed views leave gaps longer than 24 hours blank and end at the last reading. Lines connect recorded values; peaks, zeroes and reset times are never invented. Data appears after the server saves a reading at the frequency set in Settings.

## Home Assistant

The ChatGPT and Claude cards and the chart can be shown in Home Assistant, each on its own. [Home Assistant](HOME_ASSISTANT.md) explains how.
