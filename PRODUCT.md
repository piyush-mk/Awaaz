# Awaaz: the AI Munim for every Paytm merchant

> **Bolo. Dikhao. Ho gaya.** (Speak. Show. Done.)
>
> Paytm Build for India AI Hackathon, Delhi · Track 1: Merchant Growth AI

---

## 1. The idea in one paragraph

Big shops in India always had a **munim**: the person who sat at the counter, kept the bahi-khata, knew which customer pays late, argued with the distributor's salesman, counted the galla at night and told the owner what to stock before Diwali. A kirana owner today is the munim, the cashier, the stock boy and the accountant, all at once, with one notebook and a phone.

**Awaaz gives every Paytm merchant a munim.** It listens at the counter, looks at the shelf, reads the bills, remembers every rupee of udhaar and talks to customers and distributors on WhatsApp. The merchant never types. They speak, or point the phone, and the work is done.

It is not a billing app with AI added on. It is one assistant that runs the shop's whole day, and every piece of it feeds the next.

---

## 2. Why this, why now, why Paytm

**The kirana runs on three things no app has digitised well: speech, paper and trust.**

- Orders are spoken across the counter, not typed. Billing apps assume a keyboard and an idle hand, and the owner has neither.
- Stock arrives on paper (distributor bills). Credit lives on paper (the khata notebook). Customers bring paper (the parchi from home).
- Udhaar is the one thing quick commerce cannot copy. Every respondent in an Indian Chamber of Commerce survey had customers who depend on credit ([ICC](https://indianchamber.org/upload/page/pdf/quick-commerce.pdf)). But udhaar is also where kiranas lose the most money and the most sleep.

**Why now**

- Indian-language voice AI is finally good enough for a noisy shop: Sarvam's Saaras v4 understands 22 Indian languages plus English, including mixed Hindi-English speech, and streams live ([Sarvam](https://docs.sarvam.ai/api/getting-started/models)).
- Vision AI can read handwritten Hindi notes and printed invoices from a phone photo (Sarvam Vision).
- Paytm Postpaid is back as a credit line on UPI ([Inc42](https://inc42.com/buzz/paytm-relaunches-bnpl-product-as-credit-line-on-upi-service/)), so customer credit no longer has to come out of the shopkeeper's pocket.

**Why Paytm, and why only Paytm**

- Paytm already sits on the counter. It has roughly 1.5 crore subscription merchants with Soundbox and other devices ([Inc42](https://inc42.com/buzz/paytm-bets-on-ai-makeover-to-drive-fy27-momentum/)), plus a field force that installs and services them. Distribution costs nothing extra.
- Paytm's AI Soundbox can already tell a merchant *how much* they collected ([BusinessToday](https://www.businesstoday.in/tech-today/launch/story/paytm-unveils-indias-first-ai-soundbox-for-merchants-shares-jump-25-after-launch-497139-2025-10-07)). It cannot tell them *what* they sold, what is about to run out or who owes them money. **Paytm sees ₹294 arrive. Awaaz sees "2 Maggi, 1 Surf, 4 Colgate".** That item-level layer is what turns a payments company into the shop's operating system.
- Paytm has the money products the munim needs to recommend: Postpaid for customers, loans and insurance for merchants.

---

## 3. How the merchant talks to Awaaz

Three ways in, no keyboard:

| | How | Used for |
|---|---|---|
| **Bolo** (speak) | Natural speech in any Indian language, mixed with English | Billing, stock, udhaar, questions, prices |
| **Dikhao** (show) | Point the phone camera, or take one photo | Shelf, counter, bills, parchi, khata pages, cash |
| **WhatsApp** | Customers and distributors message the shop as they already do | Orders, receipts, reminders, purchase orders |

And three ways out:

- **The Soundbox voice** announces payments, totals and alerts, as it already does.
- **The phone screen** shows the cart, big and in the merchant's own script, with one-tap confirm.
- **WhatsApp** carries receipts, confirmations and reminders to customers and distributors.

**Dukaan Mode.** In production, the phone sits on a ₹200 stand at the counter, plugged in, camera facing the counter top. That is the physical product: an old phone becomes the munim's eyes and ears, next to the Soundbox that is already its voice.

---

## 4. One day at Ramesh General Store

Ramesh Gupta, 48, runs a kirana in Laxmi Nagar, Delhi. His son Rohit covers evenings. He has about 140 customers on udhaar, two regular distributors and a Paytm Soundbox. This is his Saturday with Awaaz.

### 7:00 AM · Shop opens

The Soundbox speaks, in Ramesh's language:

> *"Namaste Ramesh ji. Kal ₹8,420 ki sale hui, pichhle Saturday se 12% zyada. Teen cheezein khatam hone wali hain: Tata Namak, Aashirvaad Atta, Vim Bar. Dhanteras 6 tareekh ko hai; pichhle saal is hafte ghee aur dry fruits chaar guna bike the, aur ghee sirf do din ka bacha hai. Aaj Rajesh Distributors aayenge."*

Then the fresh-item prices. Ramesh says *"Aaj ande saat rupaye, paneer teen sau assi kilo, doodh wahi."* Every bill today uses the new rates.

### 9:30 AM · The distributor's salesman arrives

Before the salesman opens his order book, Ramesh's phone shows a short brief:

> *Surf: 14 days of stock, take 2 cartons max. Last price ₹42, don't accept more. Ask about the Diwali scheme. Return 6 Bournvita expiring next week: ₹1,140 claim.*

When the goods arrive, Ramesh photographs the bill. Awaaz reads every line: item, quantity, cost price, batch and expiry. Stock goes up, margins update, and it flags two things:

> *"Surf ₹3 mehenga aaya hai pichhli baar se. Aur bill pe 'buy 10 get 1' likha hai, par free packet nahi gina gaya."*

Ramesh catches it while the salesman is still in the shop.

### 10:00 AM to 1:00 PM · The morning rush

Ramesh never presses a button. Awaaz is listening at the counter:

- A customer says *"Bhaiya do Maggi, ek Surf, aur bees rupaye ki cheeni."* The cart fills as she speaks. "Bees rupaye ki cheeni" becomes 450 g at ₹44/kg, and the screen says **"450 gram tolo."** Ramesh says *"bas, kitna hua?"* and the Soundbox reads the total while the QR shows the exact amount. She pays, the Soundbox announces it, the stock drops and the receipt lands on her WhatsApp.
- A boy hands over a folded parchi in his mother's Hindi handwriting. Ramesh photographs it and the cart is ready. Ramesh packs, the boy pays.
- A regular buys single cigarettes and single Maggi packets. Awaaz knows the carton Ramesh bought holds 12 packets and tracks stock at both levels.
- Sharma ji pays by UPI. Awaaz recognises him from his UPI ID and suggests *"Sharma ji ka usual: 1 doodh, 1 bread, 6 ande?"* One tap.
- Someone asks for Kurkure; Ramesh doesn't stock it. He says *"Kurkure nahi hai"* and Awaaz notes a missed sale. (Later it will suggest: *"Kurkure was asked for 6 times this week."*) It also says Gupta Store, 200 m away, has it, and that Ramesh owes Gupta ji 5 Surf from last week.
- A customer says *"300 cash diya, 200 Paytm, baaki khate mein."* One bill, three payment modes, all recorded.

### Udhaar, the moment that matters most

Verma ji is short of money. Ramesh says *"Verma ji ke khate mein 500."* Two things happen:

1. Verma ji instantly gets a WhatsApp message: *"₹500 aapke khate mein jude. Kul baaki ₹1,350. Galat ho toh reply karein."* The argument about "maine toh diye the" next month never happens.
2. Awaaz quietly shows Ramesh: *"Verma ji ne pichhli 3 baar der se chukaya. Limit ₹500 tak rakhein?"* and offers an option Ramesh never had before: **"Paytm Postpaid se le lo?"** If Verma ji pays with Postpaid, Ramesh gets his money now and the credit risk sits with the bank, not with Ramesh.

### 2:00 PM · Afternoon lull

WhatsApp is where the shop earns between rushes:

- Mrs. Kapoor sends a 40-second voice note: *"Bhaiya mahine ka ration bhej do, wahi jo pichhle mahine tha, bas atta do bag."* Awaaz turns it into a packing list, sends her a payment link, and tells Ramesh which items to pack for the delivery boy.
- Someone sends a photo of a handwritten list. Same flow.

Ramesh goes to the bank. **Rohit takes over the counter.** Ramesh gets a short voice update on his phone every couple of hours: *"Do baje tak ₹4,200 ki sale, teen udhaar, sab theek."* If cash and bills ever don't match, he hears about it.

### 9:30 PM · Closing

Rohit spreads the day's cash on the counter and takes one photo. Awaaz counts the notes and checks them against every cash bill, UPI payment and udhaar entry:

> *"Galle mein ₹6,850 hona chahiye tha, ₹6,700 hai. ₹150 kam."*

It also shows what was sold today, how much udhaar went out and came back, and what to order tomorrow, with a ready purchase order that Ramesh can send to Rajesh Distributors on WhatsApp in one tap.

### Once a week · The shelf walk

Ramesh walks along his shelves with the phone camera on, about one minute per aisle. Awaaz counts what it sees and compares it with what the books say. Gaps show up as losses: damaged, expired, stolen or simply never billed.

The same video also crops a clean photo of every product. That photo set plus the stock list **is** an online catalog: a WhatsApp catalog today and an ONDC listing tomorrow, without Ramesh ever photographing a product on purpose.

### On the 1st of the month · Salary day

Most udhaar customers get paid in the first week. Awaaz sends polite reminders then, not on random days, with a payment link and in each customer's language. If Ramesh wants, the reminder plays as a voice note in **his own voice** (a voice clone he recorded once, with his consent). People respond to the shopkeeper they know, not to a bank-style text.

### Before Diwali · The munim gives advice

> *"Aapki dukaan mein ₹1.2 lakh ka verified maal hai, aur roz ki sale steady hai. Diwali stock ke liye ₹40,000 ka Paytm loan aur dukaan ke maal ka insurance, dono ek tap mein."*

The munim can say this because it has seen the stock with its own eyes (shelf walk plus distributor bills) and every sale with its own ears. **The shelf becomes the credit score.**

---

## 5. The product: five rooms of one shop

Every idea above folds into five areas that every kirana owner already thinks in, plus the network around them.

### 🧾 Counter (Galla): selling

- **Listening counter:** the cart fills from the natural conversation between merchant and customer; no button, no wake word in Dukaan Mode
- **Speak, scan or show:** voice, barcode and camera all feed the same cart; whichever is fastest for that item
- **"₹20 ki cheeni":** amount-based and weight-based selling for loose items; the screen tells the merchant how much to weigh
- **Pack-breaking:** bought by the carton, sold by the piece, tracked at both levels
- **Parchi photo:** handwritten lists from customers become carts
- **Mixed payment in one sentence:** cash plus UPI plus udhaar
- **Exact-amount QR** and automatic payment confirmation through the Soundbox
- **Receipts that work for everyone:** WhatsApp text receipt, a **voice-note receipt** read out in the customer's language, and a print for those who want one
- **Correct GST:** prices are MRP-inclusive, GST is worked out of the MRP, and small dealers on the composition scheme automatically issue a "Bill of Supply" instead of a tax invoice
- **Usual baskets:** regulars are recognised from their UPI ID
- **Daily fresh prices** set by voice each morning

### 📦 Godown: stock

- **Bill scan:** a photo of the distributor's invoice updates stock, cost prices, batches and expiry
- **Price guard:** flags price increases and schemes that weren't applied
- **Shelf walk:** weekly video audit; expected against counted stock reveals losses
- **Catalog for free:** the shelf walk also produces product photos for WhatsApp and ONDC
- **Missed sales:** "nahi hai" becomes demand data
- **Expiry return claims:** reminders to hand near-expiry stock back to the distributor on the next visit, with the batch details the claim needs
- **Smart reorder:** days of stock left, turned into a purchase order sent on WhatsApp

### 📒 Khata: credit and trust

- **Bahi-khata migration:** photograph the old notebook pages and the digital ledger is ready; years of udhaar come over in minutes
- **Udhaar by voice** with an **instant WhatsApp confirmation** to the customer
- **Credit limits** per customer based on how they have paid before
- **Salary-day reminders,** optionally in the owner's own voice
- **Paytm Postpaid at the counter:** the customer gets credit and the merchant gets cash now
- **Chhutta to khata:** no ₹2 coin? The change is credited to the customer's khata instead of handing over a toffee
- **Customer passbook:** a WhatsApp link where each customer can see their balance and pay any time

### 🧮 Hisaab: accounts and control

- **Galla scan:** one photo of the cash, counted and checked against the day's bills
- **Three-way check:** cash against bills against stock; any one out of line shows up
- **Malik ki aankh:** short voice updates when someone else is at the counter
- **Daily, weekly, monthly summaries** spoken, not printed
- **GST summary** ready for the accountant at quarter end

### 💡 Salaah: advice

- **Morning brief:** yesterday, today's risks, who's coming
- **Festival forecasting:** Diwali, Holi, Eid, wedding season, local fairs
- **Salesman coach:** a brief before every distributor visit
- **Neighbourhood insight:** *"Stores within 1 km sell 3× more Amul Lassi than you."* Only possible because Paytm sees thousands of nearby counters (anonymised and aggregated)
- **Money offers that fit the moment:** Diwali stock loan, shop insurance on verified stock value, Postpaid for customers

### 🏘️ Pados: the network around the shop

- **Stock borrowing between shops:** "Gupta ji se 5 Surf liye," recorded on both sides and settled over Paytm
- **Neighbour lookup:** "Nahi hai? Gupta Store, 200 m, has 30"
- **Later:** pooled buying across nearby kiranas to unlock distributor bulk prices

---

## 6. The ecosystem

```
                         ┌──────────────────────────┐
                         │          PAYTM           │
                         │ UPI · Soundbox · Postpaid│
                         │   Loans · Insurance      │
                         └────────────┬─────────────┘
                                      │ payments, credit, offers
                                      ▼
   CUSTOMERS  ◄── WhatsApp ──►  ┌─────────────┐  ◄── WhatsApp ──►  DISTRIBUTORS
   receipts, khata,             │   AWAAZ     │                    purchase orders,
   voice orders, parchi         │  the munim  │                    bills, expiry claims
   (no app to install)          │  in the     │
                                │  merchant's │
                                │  phone +    │
                                │  Soundbox   │
                                └──────┬──────┘
                                       │ anonymised demand,
                                       │ stock lending
                                       ▼
                               NEIGHBOURING KIRANAS
                               (the Pados network)
```

**Nobody else has to install anything.** Customers and distributors stay on WhatsApp and UPI, which they already use. Only the merchant runs Awaaz, and that merchant already has the Paytm app and a Soundbox.

---

## 7. Getting a shop onto Awaaz: 15 minutes, zero typing

The hardest part of any shop software is day one: entering hundreds of products and years of credit. Awaaz turns onboarding into four photos and one walk:

1. **Photograph the khata notebook** → every customer and balance is in the ledger.
2. **Walk the shelves with the camera** → the product catalog and opening stock are created.
3. **Photograph last month's distributor bills** → cost prices, suppliers and margins are set.
4. **Say your shop name and UPI ID** → receipts and QR are ready.

**Go-to-market:** Paytm's field agents already visit merchants to install and service Soundboxes. Awaaz onboarding becomes part of that visit. The agent leaves a phone stand at the counter. No new sales force, no ad spend.

---

## 8. Built for a real shop, not a demo stage

These are the rules that make Awaaz usable on a busy Saturday, not just in a quiet room:

- **AI proposes, merchant decides.** Nothing that moves money or stock is final until the merchant confirms, with one tap or a spoken "haan". Wrong items are fixed by saying "Maggi teen nahi, do".
- **Works through noise.** The counter is loud: traffic, TV, three customers at once. Awaaz shows what it heard on screen so mistakes are visible immediately, and it learns each shop's product names and slang over time.
- **Works through bad internet and power cuts.** Billing continues offline; payments and WhatsApp messages sync when the connection returns.
- **Runs on cheap phones.** The target is a ₹8,000 Android phone, or an old one handed down in the family.
- **Privacy by design.** Listening happens only in Dukaan Mode, with a visible "sun raha hai" indicator and a one-tap mute. Conversations are not stored; only the items and amounts are kept. Customers get WhatsApp messages only after their first purchase and can stop them with one reply.
- **Respects how the shop already works.** The khata stays the khata. The salesman still comes on Monday. Awaaz fits into existing habits instead of asking the owner to change them.
- **Speaks the merchant's language.** Every screen, announcement and reminder is in the language the owner chooses, and customer messages go out in each customer's language.

---

## 9. What it's worth

### For the merchant

These are planning estimates to validate in pilots, not measured results:

| Problem today | With Awaaz |
|---|---|
| 1 to 2 hours a day on billing, khata and stock entry | Near zero; it happens while selling |
| Udhaar disputes and forgotten entries | Every entry confirmed on WhatsApp at the moment it happens |
| Slow udhaar recovery | Salary-day reminders with a pay link; Postpaid moves new credit risk off the shop |
| Expired stock written off | Return claims prompted before the distributor's next visit |
| Distributor overcharges and missed schemes | Caught at bill scan, while the salesman is still there |
| Stock-outs on festival days | Forecast a week ahead; loan offered in time to buy |
| Cash gaps when family or staff are at the counter | Seen the same night |

### For Paytm

1. **Item-level data from every counter:** better underwriting for merchant loans, better insurance pricing, and anonymised demand insight that brands and distributors value.
2. **More credit volume:** Postpaid at the counter turns informal udhaar into Paytm credit.
3. **More money products at the right moment:** loans and insurance offered when the munim knows they are needed, not by cold call.
4. **Stickier merchants:** a shop whose khata, stock and customers live in Awaaz does not switch payment providers.
5. **A premium Soundbox tier:** Awaaz features bundled into the Soundbox subscription the merchant already pays.

### Business model

- **Free core** for every Paytm merchant: voice billing, receipts, khata.
- **Awaaz Pro** in the Soundbox subscription: shelf walk, Pados network, owner-away mode, advanced advice.
- **Revenue that scales with the merchant:** lending and insurance distribution, Postpaid volume, B2B ordering and, later, aggregated demand insights for brands.

---

## 10. Why we win against existing apps

| | Khatabook / OkCredit | Vyapar / myBillBook | Paytm AI Soundbox today | **Awaaz** |
|---|---|---|---|---|
| Input | Typing | Typing, barcode | Voice questions | **Voice, camera, WhatsApp** |
| Knows *what* was sold | No | Yes, if typed | No | **Yes, automatically** |
| Udhaar | Yes | Partial | No | **Yes, with confirmation and Postpaid** |
| Stock from bills and shelves | No | Manual | No | **Photo and video** |
| Talks to customers and distributors | SMS reminders | WhatsApp invoices | No | **Full WhatsApp loop** |
| Gives advice | No | Reports | Payment summaries | **Morning brief, forecasts, salesman coach** |
| Connects to credit and insurance | Limited | No | Paytm offers | **At the moment of need** |

The point isn't any single feature. **Awaaz is the only one where the merchant never has to stop selling to feed the software.**

---

## 11. What we show on 31 October

A three-minute story that follows Ramesh's day:

1. **Onboarding (20 s):** photograph a khata page → customers and balances appear.
2. **Distributor bill (30 s):** photograph the invoice → stock updates; the price guard flags an overcharge.
3. **The counter (60 s):** a customer speaks naturally, including "bees rupaye ki cheeni" → cart → exact-amount QR → paid → WhatsApp receipt plus voice receipt. A parchi photo becomes the next cart.
4. **Udhaar (30 s):** "Verma ji ke khate mein 500" → WhatsApp confirmation → Postpaid offered.
5. **Closing (20 s):** galla photo → ₹150 short.
6. **Next morning (20 s):** the spoken brief with the Dhanteras forecast and a one-tap purchase order.

Close: *"Paytm already knows how much every kirana earns. Awaaz tells it, and the shopkeeper, what they sell, what they owe and what to do next. A munim for 1.5 crore merchants, at zero acquisition cost."*

**Everything else in this document is the roadmap** we walk through on the vision slide: the shelf walk, Pados network, owner-away mode, voice-clone reminders and the neighbourhood insights.

---

## 12. Questions judges will ask

**"Isn't always-on listening a privacy problem?"**
Only in Dukaan Mode, with a visible indicator and one-tap mute. Audio is processed and discarded; only items and amounts are kept. The merchant confirms every bill.

**"What if the AI gets it wrong at a busy counter?"**
The cart is always on screen and every bill needs a "haan". Fixing it is spoken too ("do nahi, teen"). It is faster than typing even when it is wrong.

**"Why would a kirana owner change habits?"**
They don't have to. They keep talking to customers, keep the khata and keep meeting the salesman. Awaaz listens and writes it down.

**"Why can't Khatabook or PhonePe build this?"**
They can build pieces. Only Paytm has the Soundbox already on the counter, a field force already visiting the shop, and Postpaid, loans and insurance to plug in. The neighbourhood insight needs counter data at Paytm's scale.

**"How does Paytm make money?"**
Better lending and insurance through item-level data, Postpaid volume at the counter, a premium Soundbox tier and lower merchant churn.

---

## Sources

- Paytm AI Soundbox launch: [BusinessToday](https://www.businesstoday.in/tech-today/launch/story/paytm-unveils-indias-first-ai-soundbox-for-merchants-shares-jump-25-after-launch-497139-2025-10-07), [Analytics India Magazine](https://analyticsindiamag.com/ai-news-updates/paytm-launches-ai-powered-soundbox-for-merchants-in-11-indian-languages/)
- Paytm merchant base and AI strategy: [Inc42](https://inc42.com/buzz/paytm-bets-on-ai-makeover-to-drive-fy27-momentum/), [Paytm investor presentation, Jun 2026](https://paytm.com/document/ir/annual-reports/Paytm-Investor-Presentation_Jun-2026_INR.pdf)
- Paytm Postpaid as a UPI credit line: [Inc42](https://inc42.com/buzz/paytm-relaunches-bnpl-product-as-credit-line-on-upi-service/), [Paytm blog](https://paytm.com/blog/loan/postpaid-loan/buy-now-pay-later-how-paytm-postpaid-works/)
- Kiranas, credit and quick commerce: [Indian Chamber of Commerce](https://indianchamber.org/upload/page/pdf/quick-commerce.pdf), [Grant Thornton](https://www.grantthornton.in/globalassets/1.-member-firms/india/assets/pdfs/quick_commerce_report.pdf), [The Hans India](https://www.thehansindia.com/business/convenience-now-primary-driver-of-retail-choices-amid-quick-commerce-surge-1063452)
- GST 2.0 rates (effective 22 Sept 2025): [Business Standard](https://www.business-standard.com/amp/economy/news/gst-rate-cut-fmcg-items-to-boost-consumption-and-demand-125090400224_1.html), [Tally](https://tallysolutions.com/gst/new-gst-rate-structure/)
- FMCG returns and expiry claims: [kirana.club](https://kirana.club/resources/fmcg-returns-expiry-damages-gt), [Rework](https://resources.rework.com/libraries/fmcg-distribution-growth/returns-damages-freshness-fifo)
- Sarvam AI models: [Sarvam docs](https://docs.sarvam.ai/api/getting-started/models)
- Dhanteras 2026 (6 Nov): [Shubhpanchang](https://shubhpanchang.com/festivals/dhanteras)
- Existing AI phone-ordering for kiranas: [AI Kirana](https://www.aikirana.in/)
