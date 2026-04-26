# 1. Сохраните ваш ключ в файл

# 2. Конвертируйте его PEM формата OpenSSH
ssh-keygen -i -f pub2 > public.pem

# 3. Сконвертируйте OpenSSH в X.509 (формат для Java)
ssh-keygen -e -f public.pem -m PKCS8 > certificate_1.pem

Выполнять именно в DOS/Far, не в powershell