# Experiment report — qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42

Generated: 2026-08-30T01:27:54.609385+00:00

## Run metadata

- task: `correspondence_classification`
- prompt version: `sorter_docclass_correspondence_v0`
- model: `qwen/qwen3.7-flash`
- hf_repo: `Lucius-Morningstar/enron-correspondence-dedup`
- dataset size: `200`
- stratified / seed: `200 / 42`
- braintrust_logging: `True`
- git: `951bb6b`
- ground truth: `expected + expected_subclass + sentiment_label + sentiment_score`

## Aggregate scorers

- rows: **200** (errors: 0)
- doc_type_accuracy: **1.0000**
- subclass_accuracy: **0.4000** (equiv 0.4000)
- exact_match (doc_type ∧ subclass): **0.4000**
- sentiment_label_accuracy: **0.6300**
- sentiment_score_ok (band 0.25): **0.7790**
- sentiment_score_mae: **0.1593**
- correspondence_exact (type ∧ subclass ∧ sentiment label): **0.3050**
- confidence: **0.8572**

## Tokens / cost

- prompt tokens: `1527001`
- completion tokens: `253176`
- total cost: `—`

## Per-subclass accuracy

| subclass | accuracy | support |
|----------|----------|---------|
| attorney_demand | 0.0000 | 3 |
| demand | 0.0000 | 25 |
| email | 0.7447 | 47 |
| letter | 0.2000 | 25 |
| meeting_request | 0.6800 | 25 |
| memo | 0.1600 | 25 |
| notice | 0.4800 | 25 |
| press_release | 0.2800 | 25 |

## Subclass confusion (expected \ predicted)

| expected \ predicted | attorney_demand | demand | email | letter | meeting_request | memo | notice | other | press_release |
|---|---|---|---|---|---|---|---|---|---|
| attorney_demand | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 2 | 0 |
| demand | 0 | 0 | 18 | 1 | 0 | 0 | 1 | 4 | 1 |
| email | 0 | 1 | 35 | 3 | 2 | 0 | 2 | 4 | 0 |
| letter | 0 | 0 | 13 | 5 | 4 | 0 | 0 | 3 | 0 |
| meeting_request | 0 | 0 | 4 | 0 | 17 | 0 | 0 | 4 | 0 |
| memo | 0 | 0 | 16 | 1 | 0 | 4 | 3 | 1 | 0 |
| notice | 0 | 0 | 13 | 0 | 0 | 0 | 12 | 0 | 0 |
| other | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| press_release | 0 | 0 | 16 | 0 | 0 | 0 | 1 | 1 | 7 |

## Per-sentiment-label accuracy

| sentiment_label | accuracy | support |
|-----------------|----------|---------|
| negative | 0.1071 | 28 |
| neutral | 0.8957 | 115 |
| positive | 0.3509 | 57 |

## Sentiment confusion (expected \ predicted)

| expected \ predicted | negative | neutral | positive | unknown |
|---|---|---|---|---|
| negative | 3 | 20 | 1 | 4 |
| neutral | 0 | 103 | 7 | 5 |
| positive | 1 | 26 | 20 | 10 |
| unknown | 0 | 0 | 0 | 0 |

## Failure insights

- n_failed: **139**
- mode_counts: `{'subclass_miss': 120, 'sentiment_miss': 19}`

## Misclassification ledger

_139 rows; showing 80._

| mode | filename | expected subclass | predicted subclass | expected sent. | predicted sent. | reasoning |
|------|----------|-------------------|--------------------|-----------------|-----------------|-----------|
| subclass_miss | sanders-r/px/19. | attorney_demand | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8049, total_tokens=10097, comple |
| subclass_miss | blair-l/inbox/88. | demand | email | neutral | neutral | The document features an email-style header ('Subject:') and informal sign-off ('Thx, Jim'), clearly identifying it as an internal email. It conveys routine adm |
| sentiment_miss | bass-e/deleted_items/252. | email | email | positive | neutral | The document is an automated HTML email containing fantasy football league standings and player injury/status updates. It clearly functions as an informational  |
| subclass_miss | lay-k/all_documents/956. | letter | email | neutral | neutral | The document is an internal corporate communication with a subject line and salutation requesting transaction data for SEC Form 4 filings. It functions as an em |
| subclass_miss | jones-t/deleted_items/12. | memo | notice | neutral | neutral | The document is explicitly titled 'Notice No. 01-417' and functions as a formal administrative communication from the Exchange to its members detailing correcte |
| subclass_miss | dasovich-j/inbox/800. | press_release | email | neutral | neutral | The document is formatted as an internal email (indicated by the 'Subject:' line and informal sign-off) distributing FAQs and press release links regarding an S |
| subclass_miss | cash-m/sent_items/383. | email | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8322, total_tokens=10370, comple |
| subclass_miss | lavorato-j/old_inbox/85. | email | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8685, total_tokens=10733, comple |
| sentiment_miss | baughman-d/inbox/346. | email | email | neutral | positive | The document is an HTML-formatted promotional blast with a subject line, body copy, tracking links, and an unsubscribe option, clearly functioning as an email.  |
| sentiment_miss | germany-c/_sent_mail/3. | email | email | positive | neutral | The document is an informal internal email thread between Enron employees discussing invoice approval timing. It functions as a routine business exchange, fitti |
| subclass_miss | fischer-m/deleted_items/27. | email | notice | neutral | neutral | The document is an automated system notification informing an employee that their expense report has been approved and paid. It functions as a status notice rat |
| subclass_miss | scott-s/deleted_items/448. | email | letter | neutral | positive | The document is an internal club update formatted as an email (Subject line, informal sign-off) that announces upcoming events, requests volunteers, and offers  |
| subclass_miss | shively-h/_sent_mail/207. | email | meeting_request | neutral | neutral | The document is an internal email/calendar invitation forwarding a recurring weekly meeting schedule ('Weekly Market Intelligence Status Meeting') with specific |
| subclass_miss | lavorato-j/california/3. | email | meeting_request | negative | neutral | The document is an agenda for a scheduled call, listing discussion topics and responsible parties. Its primary function is to organize and request participation |
| sentiment_miss | germany-c/_sent_mail/80. | email | email | negative | neutral | The document is an informal email thread between two parties discussing the execution of legal documents, addendums, and related logistics. It contains standard |
| sentiment_miss | lewis-a/deleted_items/79. | email | email | neutral | positive | The document is a promotional Valentine's Day blast from eBay delivered via email. It functions as a commercial newsletter/email rather than a formal notice or  |
| subclass_miss | ybarbo-p/inbox/150. | memo | email | positive | neutral | The document is an internal email thread between Enron employees discussing the evaluation and merits of a ship demurrage claim. It contains standard email head |
| subclass_miss | kean-s/sent_items/230. | memo | email | neutral | neutral | The document is an internal corporate email thread between Enron employees coordinating the review and signature of an EEO policy memo. It functions as routine  |
| subclass_miss | bass-e/all_documents/272. | memo | letter | positive | positive | The document is an internal company announcement formatted with a 'Subject:' line, functioning as a promotional newsletter/event notice for employees. Per rule  |
| subclass_miss | hayslett-r/projects/lng__global_/1. | memo | email | positive | neutral | The document is an internal business communication coordinating project calculations and task assignments among colleagues. The 'Subject:' header and 'Regards.' |
| subclass_miss | shackleton-s/all_documents/1608. | memo | email | neutral | neutral | The document is an email transmission from counsel attaching a draft memorandum regarding pulp and paper transactions. It functions as a routine business email  |
| subclass_miss | hain-m/all_documents/897. | memo | email | neutral | neutral | The document contains an email subject line, a standard electronic confidentiality disclaimer, and a law firm signature block, clearly identifying it as an emai |
| subclass_miss | jones-t/all_documents/5972. | memo | email | neutral | neutral | The document features a 'Subject:' header and direct, conversational business language ('Brent Hendry says...', 'Thanks!') characteristic of an internal or inte |
| subclass_miss | mcconnell-m/all_documents/851. | memo | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=8567, total_tokens=10613, comple |
| subclass_miss | ermis-f/inbox/666. | memo | notice | neutral | neutral | The document is explicitly titled 'NWP System Notice' and functions as a formal business/regulatory notice to all shippers regarding updated fuel factors and ra |
| subclass_miss | sanders-r/all_documents/255. | memo | email | negative | neutral | The document is formatted as an internal business email with a subject line and signature, providing a routine status update on deposition schedules and questio |
| subclass_miss | dickson-s/all_documents/132. | memo | email | neutral | neutral | The document features a 'Subject:' line and 'Re: FW:' threading typical of an email. Its content is a brief, routine internal update regarding forwarding a memo |
| subclass_miss | rogers-b/all_documents/440. | memo | email | neutral | positive | The document is an informal email thread between colleagues scheduling a lunch meeting, evidenced by standard email headers (To, cc, Subject, timestamp) and con |
| subclass_miss | nemec-g/all_documents/5291. | memo | email | neutral | neutral | The document uses a 'Subject:' line and direct salutation, identifying it as an internal email. Its content delivers routine operational instructions for docume |
| subclass_miss | fossum-d/all_documents/588. | memo | email | neutral | neutral | The document is an internal corporate email thread detailing a messaging system glitch that erroneously sent past luncheon invitations. It features standard ema |
| subclass_miss | kean-s/all_documents/5045. | memo | email | positive | neutral | The document is an internal email thread with standard headers (To, cc, Subject, timestamps) and brief routing messages regarding a memo's approval and distribu |
| subclass_miss | corman-s/all_documents/9. | memo | email | neutral | neutral | The document is a threaded email exchange containing administrative dial-in instructions and scheduling details for conference calls. Its structure (TO/FROM/RE  |
| subclass_miss | shackleton-s/all_documents/8952. | memo | notice | neutral | neutral | The document is a formal market notice announcing margin rate changes for specific futures contracts. It uses standard notice formatting (Notice No., TO/FROM/SU |
| sentiment_miss | steffes-j/inbox/419. | memo | memo | positive | neutral | The document explicitly uses a MEMORANDUM header with TO/FROM/DATE/RE fields, functioning as an internal policy coordination memo regarding a regulatory comment |
| subclass_miss | haedicke-m/all_documents/2407. | memo | email | neutral | neutral | The document contains standard email headers (From, Date, Subject, MIME-Version) and a brief forwarding note ('The first attempt got bounced back. Please see th |
| subclass_miss | sanders-r/all_documents/2141. | memo | email | neutral | neutral | The document is clearly formatted as an email, featuring a subject line, forwarding body text, and a standard attorney-client confidentiality footer. Its conten |
| subclass_miss | dasovich-j/all_documents/8769. | memo | email | negative | neutral | The document contains standard email headers (To, cc, Subject, timestamp) and functions as an internal message thread assigning follow-up tasks to colleagues re |
| subclass_miss | mann-k/_sent_mail/2750. | notice | email | positive | neutral | The document is an internal email thread between Enron employees discussing contract details and project timelines. It features standard email headers and routi |
| subclass_miss | hyatt-k/projects/28. | notice | email | positive | positive | The document is a threaded email exchange between project stakeholders discussing pipeline pressure specifications, operational constraints, and scheduling a fo |
| subclass_miss | dasovich-j/all_documents/4411. | notice | email | neutral | neutral | The document is formatted as an email thread with standard headers, forwarding markers, and signature blocks. Its function is purely informational, sharing a li |
| subclass_miss | dasovich-j/all_documents/10684. | notice | email | negative | neutral | The document is a compiled news digest/email forwarding multiple press articles and headlines regarding Enron and related markets, indicated by the 'Subject:' h |
| subclass_miss | mann-k/_sent_mail/2184. | notice | email | neutral | neutral | The document contains explicit email headers (From, To, Subject) and an informal, internal exchange between colleagues regarding proofreading a notice of exerci |
| sentiment_miss | jones-t/all_documents/5967. | notice | notice | positive | neutral | The document functions as a formal regulatory notice ('Notice No. 00-421') from the Exchange to its members regarding temporary price fluctuation limit rules. A |
| subclass_miss | germany-c/_sent_mail/1345. | notice | email | neutral | neutral | The document is an internal email thread between Enron employees discussing the expiration and planned termination of a storage contract. Standard email headers |
| subclass_miss | lokay-m/all_documents/206. | notice | email | positive | neutral | The document is an internal email thread from Lorraine Lindberg to colleagues requesting a summary of transport options in customer contracts. It follows standa |
| subclass_miss | platter-p/deleted_items/11. | notice | email | positive | positive | The document is formatted as a promotional email with a subject line, embedded tracking links, and an unsubscribe option. Its substantive function is marketing/ |
| subclass_miss | haedicke-m/all_documents/5022. | notice | email | neutral | neutral | The document contains a clear email subject line, a brief body forwarding background materials for an upcoming conference call, and a standard professional sign |
| subclass_miss | rapp-b/inbox/115. | notice | email | positive | neutral | The document is an internal email thread regarding employee transfer paperwork, formatted with standard email headers and informal workplace instructions. It fu |
| subclass_miss | kitchen-l/_americas/mexico/6. | notice | email | neutral | neutral | The document is formatted as an email (indicated by the 'Subject:' line) and functions as a routine business clarification regarding a contractual notice obliga |
| subclass_miss | hain-m/all_documents/250. | notice | email | neutral | neutral | The document features an email-style 'Subject:' header, informal salutation and sign-off ('Hello, Everyone', '- Bud'), and a P.S., clearly identifying it as an  |
| subclass_miss | thomas-p/deleted_items/543. | notice | email | positive | neutral | The document is a daily industry news digest distributed via email, evidenced by the 'Subject:' header, subscription management instructions at the bottom, and  |
| subclass_miss | kean-s/all_documents/8890. | letter | email | positive | neutral | The document contains an explicit email header ('Subject:') and standard email formatting (salutation, body, sign-off, attachment list), classifying it as an em |
| subclass_miss | horton-s/all_documents/69. | letter | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=8040, total_tokens=10086, comple |
| subclass_miss | smith-m/inbox/419. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8937, total_tokens=10985, comple |
| subclass_miss | ring-r/deleted_items/289. | letter | email | positive | positive | The document is a direct welcome message sent electronically to a new subscriber, explicitly identifying itself as an email and containing account details, feat |
| subclass_miss | lay-k/all_documents/565. | letter | email | positive | neutral | The document contains standard email headers (From, To, Subject) and functions as a routine business follow-up and clarification regarding a prior real estate p |
| sentiment_miss | mims-thurston-p/deleted_items/67. | letter | letter | neutral | positive | The document is a broadcast welcome message/newsletter from Amazon to new customers introducing site features. Per rule 41, an email announcing a newsletter to  |
| subclass_miss | kaminski-v/all_documents/9712. | letter | meeting_request | positive | positive | The document is a direct business message proposing a follow-up visit and conversation to explore shared professional interests. Its core function is to arrange |
| subclass_miss | campbell-l/inbox/344. | letter | email | negative | neutral | The document is an email from NYISO Customer Relations to market participants announcing a software deployment delay and new data postings. Its format (Subject  |
| subclass_miss | buy-r/inbox/438. | letter | meeting_request | negative | positive | The document is a formal invitation to speak at a conference, requesting the recipient's participation and a timely response. Its primary function is to request |
| subclass_miss | lucci-p/deleted_items/421. | letter | email | positive | positive | The document is a promotional mass-mailer with a subject line and unsubscribe footer, clearly functioning as correspondence. It is subclassed as an email based  |
| subclass_miss | ruscitti-k/inbox/279. | letter | email | positive | positive | The document contains a subject line, salutation, promotional body text, and sign-off, explicitly referencing itself as an e-mail later in the footer. It functi |
| subclass_miss | lay-k/all_documents/455. | letter | meeting_request | positive | positive | The document is an executive email confirming logistics for a forthcoming meeting to explore a strategic alliance. Its primary function is to confirm attendance |
| subclass_miss | campbell-l/inbox/669. | letter | meeting_request | neutral | neutral | The document is an email scheduling a specific working group meeting, providing date, time, physical location, and teleconference details. Per rule 41, classifi |
| subclass_miss | shackleton-s/all_documents/8895. | letter | email | positive | neutral | The document uses standard email formatting (Subject header, salutation, sign-off with contact details) and functions as a routine corporate inquiry regarding e |
| subclass_miss | love-p/personal/55. | letter | email | neutral | neutral | The document is a transactional email from the Auburn Ticket Office confirming the shipment of season tickets and providing a UPS tracking number. The presence  |
| subclass_miss | kaminski-v/all_documents/5939. | letter | email | positive | neutral | The document contains standard email formatting markers ('Subject:', 'Dear Colleague,', 'Best regards', and a mailto link) and functions as a routine access rem |
| subclass_miss | thomas-p/deleted_items/183. | letter | email | neutral | neutral | The document follows a standard email format with a subject line, salutation, brief body distributing meeting attachments, and a mailing-list footer. Its functi |
| subclass_miss | rogers-b/deleted_items/302. | letter | email | negative | neutral | The document is a mailing-list/email notification from NYISO to market participants detailing a system issue (SCD) and its resolution. The presence of a subject |
| subclass_miss | smith-m/deleted_items/47. | letter | other | positive | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2048, prompt_tokens=8806, total_tokens=10854, comple |
| subclass_miss | hendrickson-s/deleted_items/147. | letter | email | positive | positive | The document is a promotional email from Amazon.com reminding customers of a Father's Day discount offer. It features standard email formatting (Subject line, s |
| sentiment_miss | lay-k/all_documents/240. | letter | letter | negative | neutral | The document is a formal announcement to USIBC members regarding the cancellation of a San Francisco event and an updated Washington D.C. agenda. Per rule 41, a |
| subclass_miss | grigsby-m/all_documents/7. | press_release | email | neutral | neutral | The document is a routine mailing-list email from a state energy commission web team distributing a link to a posted news release about a power plant site heari |
| subclass_miss | kitchen-l/_americas/eol/2. | press_release | email | neutral | neutral | The document is formatted as an internal email with a subject line, direct salutation, and informal sign-off, functioning as a routine project schedule distribu |
| subclass_miss | shapiro-r/broadband_services/42. | press_release | email | negative | neutral | The document opens with a 'Subject:' line, uses informal internal shorthand ('w/', 'c.d.t.'), and presents a bulleted status update on regulatory and legislativ |
| subclass_miss | kitchen-l/sent_items/612. | press_release | other | neutral | None | error: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=2046, prompt_tokens=8420, total_tokens=10466, comple |
| sentiment_miss | thomas-p/deleted_items/12. | press_release | press_release | neutral | positive | The document is an automated email alert that forwards a corporate news release announcing record earnings. Per rule 41, classification follows the communicatio |
| subclass_miss | shankman-j/inbox/53. | press_release | email | neutral | neutral | The document is an informal business message between colleagues with a standard email header (Subject:) and sign-off ('Regards - Jeremy'). It functions as a rou |
| subclass_miss | kean-s/all_documents/6036. | press_release | email | neutral | neutral | The document is an internal email forwarding a draft press release for executive approval regarding the invocation of a government guarantee. It features standa |
| sentiment_miss | grigsby-m/all_documents/132. | press_release | press_release | positive | neutral | The document is explicitly titled 'NEWS RELEASE' and follows standard press release conventions, including a 'For immediate release' dateline, media contact inf |
