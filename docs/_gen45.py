import sys
sys.stdout.reconfigure(encoding="utf-8")
P=chr(124)
f=open("docs/CODE_REVIEW_STAGE4_5_TASKS_UTILS.md","a",encoding="utf-8")
f.write("### 3. push_tasks.py\n\n"+P+" # "+P+" Серьёзность "+P+" Проблема "+P+" Строка "+P+" Рекомендация "+P+"\n")
pts=[("1","MEDIUM","cleanup_expired_subscriptions загружает ВСЕ подписки -- worker заблокирован","72-100","Пагинация limit=100 + time.sleep"),("2","MEDIUM","user_id: str vs int inconsistency","16","Унифицировать как str"),("3","MEDIUM","retry без проверки не-повторяемых ошибок","48-55","410 Gone - подписку"),("4","LOW","default_retry_delay переопределяется","15,54","Убрать из декоратора"),("5","LOW","нет MaxRetriesExceededError","58","autoretry_for")]
for r in pts: f.write(P+r[0]+P+r[1]+P+r[2]+P+r[3]+P+r[4]+P+"\n")
f.close()
print("gen done")