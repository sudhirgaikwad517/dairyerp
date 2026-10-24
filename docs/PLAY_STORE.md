# Play Store release: Akash Dairy

Everything needed to publish the app on Google Play from the Prowexa Technologies developer account.

| Item | Value |
|---|---|
| App name | Akash Dairy |
| Package name | `in.akashdairyfarm.app` (cannot be changed after the first upload) |
| Version | from `pubspec.yaml` (`1.0.0+1`: versionName 1.0.0, versionCode 1). Raise the `+N` number for every new upload. |
| Server | https://app.akashdairyfarm.in |
| Privacy policy | https://app.akashdairyfarm.in/privacy |
| Terms | https://app.akashdairyfarm.in/terms |
| Account deletion | https://app.akashdairyfarm.in/delete-account (and in the app: Menu → Delete my account) |
| Store images | `docs/play-store/` (icon 512, feature graphic 1024x500, phone screenshots 1080x1920) |

## 1. Upload key (keep it safe)

- Key file: `mobile_app/dairy_customer_app/android/app/upload-keystore.jks`
- Passwords: `mobile_app/dairy_customer_app/android/key.properties`
- Both are kept out of git. **Copy both files to a safe place** (pen drive and Google Drive). Every update must be signed with this key.
- Turn on **Play App Signing** (the default) when you upload. Google then holds the real app signing key, and a lost upload key can be reset through Play support.

## 2. Build the bundle

```
cd mobile_app/dairy_customer_app
flutter build appbundle --release --dart-define=API_BASE_URL=https://app.akashdairyfarm.in/api/v1
```

The output is `build/app/outputs/bundle/release/app-release.aab`. The build ends with "failed to strip debug symbols" only because the Android SDK command-line tools are not installed on this PC. The bundle is still built correctly: the libraries are stripped and the symbols are packed in it for crash reports.

## 3. Demo login for the reviewer (App access)

The app only works after login, so Google needs a working login.

1. Admin panel → B2B Customers → Add customer:
   - Name: `Play Store Review (Demo)`
   - Mobile: a 10-digit number not used by anyone else
   - Address: any
   - **Do not assign a route**, so the reviewer's test orders never go to a delivery boy. You will get a "Not dispatched" notice instead, which you can ignore.
2. Customer → Login: set a password.
3. Play Console → App content → App access → "All or some functionality is restricted":
   - Instructions: `Choose "Customer" on the login screen. Mobile number: <number>. Password: <password>. The account is a demo customer of the dairy. Orders placed with it are not delivered.`
4. Keep this login working until the review is over (and for later updates).

## 4. Store listing

- **App name:** Akash Dairy
- **Short description (80 chars max):** Order fresh Gir cow milk daily, track deliveries, bills and payments.
- **Full description:**

```
Akash Dairy is the official app for customers of Akash Dairy Farm, Pune.

Order milk for the next morning, change or cancel it before the cut-off time, and see each delivery as it happens.

• Order milk and other dairy products for any day, with the quantity you need
• Change or cancel an order till the cut-off time shown in the app
• See today's delivery: what was delivered and when
• Report a problem (spoiled, short or missed milk) with photos; approved amounts are reduced from your bill
• See your bills, download them as PDF and check your account statement
• See your dues: unpaid bills plus milk delivered but not billed yet
• Notifications for orders, deliveries, bills and payments
• Call the dairy from the app

The app is for registered customers of Akash Dairy Farm. Your login is created by the dairy. To become a customer, call the dairy.
```

- **Category:** Food & Drink
- **Contact email / phone / website:** the dairy's details; website https://app.akashdairyfarm.in

## 5. App content answers

- **Ads:** No ads.
- **Target audience:** 18 and over. Not designed for children.
- **Content rating questionnaire:** Category "Utility, Productivity, Communication or Other". Answer No to violence, sexual content, language, drugs, gambling and user-to-user content sharing. Result: Everyone / 3+.
- **News app:** No. **Government app:** No. **COVID-19:** No.
- **Financial features:** None (the app shows bills and dues but takes no payments).
- **Health:** None.
- **Data safety:**
  - Collects data: Yes. Shares data with third parties: **No** (the hosting provider only stores data for the dairy).
  - Encrypted in transit: **Yes** (HTTPS only).
  - Users can ask for deletion: **Yes**, URL https://app.akashdairyfarm.in/delete-account
  - Data types (all "Collected", not shared, purpose **App functionality** and **Account management**, required unless noted):
    - Personal info → Name, Phone number, Address, Email address (optional)
    - Financial info → Purchase history (orders, bills, payments)
    - Photos and videos → Photos (optional; only photos the user picks for a problem report)
    - App info and performance → none. Location, contacts, device IDs, advertising ID → none.

## 6. Release steps

1. Fill Dairy Settings in the admin panel: **contact email and address** (they appear on the privacy and terms pages).
2. Play Console → Create app: name "Akash Dairy", App, Free, accept declarations.
3. Fill everything in "App content" (section 5) and "Store listing" (section 4).
4. Testing → **Internal testing** → create release → upload `app-release.aab` → add your own email as tester → install from the Play link and check login, orders and bills.
5. Production → create release with the same bundle → Send for review.

## 7. Notes

- Phones that have the old APK (package `com.dairyerp.dairy_customer_app`) see the Play app as a separate app. Uninstall the old one after installing from Play.
- After the Play release, link customers to the Play Store page rather than the APK on the website. An APK signed with the upload key cannot be updated from Play, and Play cannot update it either.
