# Post-deploy test checklist

Test on the deployed HTTPS site with a real phone. Microphone and camera do not work over plain HTTP.

**Before you start**
- Check `/status`: Sarvam shows live, then press **Reset demo data**.
- Phone: open `/app` and allow the mic and camera.
- Laptop: open `/soundbox` (click once to enable sound) and `/wa` side by side.

"Live" below means the other screen changes within about 2 seconds, with no refresh.

## 0. Language and Sarvam

| # | Do | Expect |
|---|---|---|
| 0a | Open a new phone or private window | App starts in Hindi |
| 0b | Three-dot menu, tap English | Whole merchant app switches at once. Room names become Counter, Stock, Credit, Accounts, Advice |
| 0c | Reload, then switch back to हिंदी | Choice is remembered on that phone; numbers and bills are untouched |
| 0d | Walk every room in English | No Hinglish in buttons, tabs or labels. Spoken replies, written answers, the brief and bill warnings are still Hinglish |
| 0e | Walk every room in Hindi | Full Devanagari. Some demo names stay English (Khan sahab, Bread) because the data has no Hindi name |
| 0f | `/status` | Sarvam live, models show `saaras:v4` and `bulbul:v4-flash` |
| 0g | Listen to any spoken reply | New voice is clear and says rupee amounts naturally. Tell me if you prefer another voice |

The steps below use the Hindi-mode Hinglish names from earlier builds; in English mode the same buttons read Make bill, Yes, Got paid and so on.

## 1. Counter

| # | Do | Expect |
|---|---|---|
| 1 | Hold the mic in the nav, say "do Maggi, ek Surf Excel, chaar Colgate", release | Full-screen listening with bars that move with your voice, then the receipt: Maggi 2, Surf 1, Colgate 4, and Rs249 on the Bill banao button. Live on the Soundbox |
| 2 | Tap the mic once, speak, tap the orange stop button | Same result as holding |
| 3 | Tap the mic, then the X | Closes, nothing sent |
| 4 | Say "bees rupaye ki cheeni" | "450 gram tolo" in orange on the phone and the Soundbox |
| 5 | Say "Maggi do nahi teen" | Maggi changes to 3, total updates |
| 6 | Tap a line, use + and -, then the bin | Total updates each time, line removed |
| 7 | Tap "Sunta rahe" (it changes to "Sun raha"), speak with no button, pause | Bill fills by itself. It should not hear its own spoken reply |
| 8 | Say gibberish, or cough | "Samajh nahi aaya" or similar. **Nothing is added to the bill** |
| 9 | Tap the keyboard icon in the header, type "ek surf excel" | Same as speaking |
| 10 | Tap Customer, pick one with a usual basket | "usual?" prompt; Haan adds it |
| 11 | Tap Parchi, photograph a handwritten list | Cart fills. Anything unknown shows a "nahi hai" button to note it |

## 2. Payment

| # | Do | Expect |
|---|---|---|
| 12 | Bill banao, tap Paytm | Exact-amount QR on the phone and the Soundbox. Scan with a UPI app without paying: the amount is pre-filled and correct |
| 13 | Press Payment aa gaya | Green tick, amount and spoken confirmation; Soundbox shows received; stock drops; WhatsApp receipt in `/wa` |
| 14 | Reload the phone | Does not show the old paid screen again |
| 15 | New bill, tap Cash | Completes straight away with no QR. Sheet closes |
| 16 | New bill, tap Mix, enter Rs100 cash and Rs50 khata | Button names the Paytm remainder; khata asks for a customer first; QR shows only the remainder |
| 17 | Open the pay sheet on the next bill | Shows the four choices again, nothing left over from the last bill |
| 18 | Open a receipt link | Public receipt page opens and shows correct GST |

## 3. Godown (stock)

| # | Do | Expect |
|---|---|---|
| 19 | Say "das packet Maggi" | Haan/Nahi card. Stock unchanged until Haan, then up by 10 live |
| 20 | Read the stock list | Only a problem gets a second line (Aaj khatam, Kam hai, expiry). Fine items show just name and quantity |
| 21 | Photograph a real distributor bill | Problem lines come first, tagged +Rs3 or "free nahi mila". The details are spoken. Haan adds to stock |
| 22 | Scan the same bill again | Warned that it was already entered |
| 23 | Photograph a blurry or blank page | "Bill padh nahi paya" with a retake button, not a fake bill |
| 24 | Photograph a real shelf | Counts are believable; you can correct them before Haan |
| 25 | Open Expiry and switch 7/15/30 din | Claim amount changes |
| 26 | Open Nahi mila and note "kurkure" | Count goes up |

## 4. Khata (credit)

| # | Do | Expect |
|---|---|---|
| 27 | In Khata, say "Verma ji ke khate mein paanch sau" | Haan/Nahi with a short over-limit warning. After Haan: balance live on a second open phone, and WhatsApp message in `/wa` |
| 28 | Open Verma ji, tap Udhaar diya, tap 200 | Button reads "Udhaar likho Rs200". After it: new balance, "WhatsApp bheja", and a Postpaid offer if over limit. It must say simulated |
| 29 | Tap Paisa mila, tap an amount, Jama karo | Balance drops on the page right away |
| 30 | In `/wa`, reply as the customer that an entry is wrong | Phone warns and marks the entry live |
| 31 | Check the customer passbook link | Page opens with the correct balance |
| 32 | Bell icon, Haan | Messages appear in `/wa`, each with a pay link |
| 33 | Camera icon, photograph a real notebook page | Names and amounts match; you can edit; Haan adds them |

## 5. Hisaab (accounts)

| # | Do | Expect |
|---|---|---|
| 34 | Keep Hisaab open on one phone, sell on another | Sale number and chart update live. Also try a cash-only bill |
| 35 | Say "aaj sabse zyada kya bika?" | Spoken answer matches the list on screen |
| 36 | Open Bill and tap one | Today's bills, receipt opens |
| 37 | Galla: photograph real cash | Note counts are close and editable; expected vs counted is right; closing announces the difference |
| 38 | Galla: tap Ginein | Totals add up correctly |

## 6. Salaah (lightbulb in the header)

| # | Do | Expect |
|---|---|---|
| 39 | Open Aaj, press Sunein and the Soundbox icon | Brief speaks on both. Tap Padhein to read it. **Facts must match the screens** (the wording comes from the LLM) |
| 40 | Order: Order banao, change a quantity, send | Purchase order appears in `/wa` |
| 41 | Puchhein: "Verma ji ka kitna baaki hai?" | Correct amount, written like Rs850 and not Rs850.0 |
| 42 | In `/wa`, send a voice note as a customer | Order appears live on the WhatsApp tab |
| 43 | Tap Bill banao on that order | Moves to Counter and leaves the order list |

## 7. Live and failure behaviour

| # | Do | Expect |
|---|---|---|
| 44 | Turn the phone's internet off and on | Header shows offline, then recovers. Events missed in between arrive, old payments do not replay |
| 45 | Press Reset demo data with the phone open | Numbers reset without a refresh |
| 46 | Refuse the mic permission | Clear message, and typing still works |
| 47 | Look through every screen | No word "munim", no long sentences, no sideways scrolling, every icon's meaning is obvious, and the mic never hides the last row or a button |

## 8. Real WhatsApp, only if `WA_TOKEN` is set

| # | Do | Expect |
|---|---|---|
| 48 | Send "hi" from your phone to the test number, then repeat steps 13 and 27 using that number | Real messages arrive. Delivery status updates in `/wa` |

## Not verified before this list

These need a real phone, real paper and the deployed site:
- Real voices in a noisy room; so far speech was tested with generated Hindi audio through Chrome's microphone
- iPhone Safari (audio format and autoplay)
- Vision on real photos of cash, shelves and notebook pages; only a rendered bill and parchi were read live
- Real WhatsApp delivery and real UPI settlement (payment is simulated)
