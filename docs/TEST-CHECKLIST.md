# Post-deploy test checklist

Test on the deployed HTTPS site with a real phone. Microphone and camera do not work over plain HTTP.

**Before you start**
- Check `/status`: Sarvam shows live, then press **Reset demo data**.
- Phone: open `/app` and allow the mic and camera.
- Laptop: open `/soundbox` (click once to enable sound) and `/wa` side by side.

"Live" below means the other screen changes within about 2 seconds, with no refresh.

## 1. Counter

| # | Do | Expect |
|---|---|---|
| 1 | Hold the mic in the nav, say "do Maggi, ek Surf Excel, chaar Colgate", release | Full-screen listening with bars that move with your voice, then the receipt: Maggi 2, Surf 1, Colgate 4, Rs249. Live on the Soundbox |
| 2 | Tap the mic once, speak, tap the orange stop button | Same result as holding |
| 3 | Tap the mic, then the X | Closes, nothing sent |
| 4 | Say "bees rupaye ki cheeni" | "450 gram tolo" in orange on the phone and the Soundbox |
| 5 | Say "Maggi do nahi teen" | Maggi changes to 3, total updates |
| 6 | Tap a line, use + and -, then the bin | Total updates each time, line removed |
| 7 | Turn on "Sun raha hai", speak with no button, pause | Bill fills by itself. It should not hear its own spoken reply |
| 8 | Say gibberish, or cough | "Samajh nahi aaya" or similar. **Nothing is added to the bill** |
| 9 | Type on the keyboard icon: "ek surf excel" | Same as speaking |
| 10 | Pick a customer who has a usual basket | "usual?" prompt; Haan adds it |
| 11 | Photograph a handwritten parchi | Cart fills. Anything unknown offers "nahi hai: note karein" |

## 2. Payment

| # | Do | Expect |
|---|---|---|
| 12 | Bill banao, Paytm, Haan | Exact-amount QR on the phone and the Soundbox. Scan with a UPI app without paying: the amount is pre-filled and correct |
| 13 | Press Payment aa gaya | Paid screen and spoken confirmation; Soundbox shows received; stock drops; WhatsApp receipt in `/wa` |
| 14 | Reload the phone | Does not show the old paid screen again |
| 15 | New bill, Cash, Haan | Completes with no QR. Sheet closes |
| 16 | New bill, Mix: Rs100 cash + Rs50 khata + rest UPI | QR shows only the remainder; khata asks for a customer first |
| 17 | Open the pay sheet on the next bill | Starts on Paytm again, nothing left over from the last bill |
| 18 | Open a receipt link | Public receipt page opens and shows correct GST |

## 3. Godown (stock)

| # | Do | Expect |
|---|---|---|
| 19 | Say "das packet Maggi" | Haan/Nahi card. Stock unchanged until Haan, then up by 10 live |
| 20 | Read the stock list | Each row shows one status. No green dot next to a red warning |
| 21 | Photograph a real distributor bill | Items, rates and flags (price rise, free packet) match the paper. Haan adds to stock |
| 22 | Scan the same bill again | Warned that it was already entered |
| 23 | Photograph a blurry or blank page | "Padh nahi paya, doosri photo", not a fake bill |
| 24 | Photograph a real shelf | Counts are believable; you can correct them before Haan |
| 25 | Open Expiry and switch 7/15/30 din | Claim amount changes |
| 26 | Open Nahi mila and note "kurkure" | Count goes up |

## 4. Khata (credit)

| # | Do | Expect |
|---|---|---|
| 27 | In Khata, say "Verma ji ke khate mein paanch sau" | Haan/Nahi with an over-limit warning. After Haan: balance live on a second open phone, and WhatsApp message in `/wa` |
| 28 | Open Verma ji, tap Udhaar diya, enter an amount | Confirm, then Postpaid offer if over limit. It must say simulated |
| 29 | Tap Paisa mila | Balance drops on the page right away |
| 30 | In `/wa`, reply as the customer that an entry is wrong | Phone warns and marks the entry live |
| 31 | Check the customer passbook link | Page opens with the correct balance |
| 32 | Reminder, Haan | Messages appear in `/wa`, each with a pay link |
| 33 | Photograph a real notebook page | Names and amounts match; you can edit; Haan adds them |

## 5. Hisaab (accounts)

| # | Do | Expect |
|---|---|---|
| 34 | Keep Hisaab open on one phone, sell on another | Sale number and chart update live. Also try a cash-only bill |
| 35 | Say "aaj sabse zyada kya bika?" | Spoken answer matches the list on screen |
| 36 | Open Bill and tap one | Today's bills, receipt opens |
| 37 | Galla: photograph real cash | Note counts are close and editable; expected vs counted is right; closing announces the difference |
| 38 | Galla: tap Haath se ginein | Totals add up correctly |

## 6. Salaah (lightbulb in the header)

| # | Do | Expect |
|---|---|---|
| 39 | Open Aaj, press Sunein and Soundbox par | Brief speaks on both. **Read it: facts must match the screens** (the wording comes from the LLM) |
| 40 | Order: Aaj ka order banao, change a quantity, send | Purchase order appears in `/wa` |
| 41 | Puchhein: "Verma ji ka kitna baaki hai?" | Correct amount, written like Rs850 and not Rs850.0 |
| 42 | In `/wa`, send a voice note as a customer | Order appears live on the WhatsApp tab |
| 43 | Tap Bill banao on that order | Moves to Counter and leaves the order list |

## 7. Live and failure behaviour

| # | Do | Expect |
|---|---|---|
| 44 | Turn the phone's internet off and on | Header shows offline, then recovers. Events missed in between arrive, old payments do not replay |
| 45 | Press Reset demo data with the phone open | Numbers reset without a refresh |
| 46 | Refuse the mic permission | Clear message, and typing still works |
| 47 | Look through every screen | No word "munim", no sideways scrolling, and the mic never hides the last row or a button |

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
