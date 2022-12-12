from django.core.mail import EmailMessage
import os
import random



class Util:
  @staticmethod
  def send_email(data):
    otp = random.randint(1000,9999)
    email = EmailMessage(
      subject=data['subject'],
      body=data['body'],
      
      #from_email=os.environ.get('EMAIL_FROM'),
      from_email='amanpandey.tecbic@gmail.com',
      to=[data['to_email']]
      
    )
    print(email)
    email.send()