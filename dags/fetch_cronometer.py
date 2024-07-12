from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from cronometer_credential import username, password
driver =  webdriver.Firefox()

driver.get("https://www.cronometer.com/login/")

wait = WebDriverWait(driver, 20)
email_field = wait.until(EC.visibility_of_element_located((By.ID, "username")))
password_field = wait.until(EC.visibility_of_element_located((By.ID, "password")))
#submit_button = wait.until(EC.element_to_be_clickable((By.ID, "LOG IN")))
submit_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[span[@id="login_txt"]]')))

email_field.send_keys(username)
password_field.send_keys(password)


submit_button.click()

print("Submitted")

print(driver.title)


driver.quit()