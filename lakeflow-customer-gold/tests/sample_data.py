AS_OF = "2026-09-01 00:00:00"
TS = "2026-08-30 12:00:00"
DATA = {
 "customers": [("C1"," Alice ","alice@example.com","us",TS,TS)],
 "accounts": [("A1","C1","open","2020-01-01",TS,TS)],
 "products": [("P1","Payments","payments",'{"all":[{"tag":"online"},{"not":{"tag":"trusted"}}]}',TS,TS)],
 "reference_data": [("USD","2026-08-30","1",TS,TS)],
 "transactions": [
  ("T1","A1","P1","usd","100","2026-08-30 10:00:00","posted",'["Online","online"]',TS,TS),
  ("T1","A1","P1","usd","90","2026-08-30 10:00:00","posted",'[]',"2026-08-29 12:00:00",TS),
  ("T2","A1","P1","USD","-20","2026-08-30 11:00:00","POSTED",'["trusted"]',TS,TS),
  ("T3","MISSING","P1","USD","50","2026-08-30 11:00:00","POSTED",'[]',TS,TS),
  ("T4","A1","P1","USD","10","2026-08-30 11:30:00","POSTED",'[]',TS,TS),
  ("T5","A1","P1","USD","5","2026-08-30 11:30:00","PENDING",'[]',TS,TS),
 ]
}
