import json

from rest_framework.views import APIView
from .renderers import UserRenderer
from .serializers import PhoneOtpSerializer, UserLoginSerializer, UserRegistrationSerializer, VerifyAccountSerializer, \
    ResendOtpSerializer, VerifyAccountSerializerLogin, FrequentlyAskedQuestionSerializer, UserKycVerificationSerializer,\
    VehicleReportSerializer, ChangePasswordSerializer, CustomerSatisfactionSerializer, PaymentModelSerializer, \
    UserPaymentAccountSerializer, RideStartStopSerializer, NotificationSerializer, AdminUserLoginSerializer, AdminUserRegistrationSerializer,\
    GetAllUserSerializer, RideRunningTimeGet, GetAllKycUserSerializer, UserRideSerializer, UserRideDetailsSerializer, \
    GetAllUsersSerializer
import ast
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from rest_framework.pagination import LimitOffsetPagination
from rest_framework import generics
from django.db.models import Sum
from rest_framework.response import Response
from rest_framework import status
from .emails import *
from .models import FrequentlyAskedQuestions, CustomerSatisfaction, UserPaymentAccount, PaymentModel, Vehicle, \
    RideTable, NotificationModel, RideTimeHistory
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from decouple import config
from django.contrib.auth.hashers import check_password, make_password
import datetime
import requests
import time
from elekgo_app.authentication import JWTAuthentication, create_access_token, create_refresh_token, decode_access_token, decode_refresh_token
from rest_framework.permissions import IsAuthenticated
from django.contrib.sessions.backends.db import SessionStore
import environ
from dotenv import load_dotenv
load_dotenv()






env = environ.Env()
environ.Env.read_env()

# Using Nominatim Api
geolocator = Nominatim(user_agent="coordinateconverter")
def get_sec(time_str):
    h, m, s = time_str.split(':')
    return int(h) * 3600 + int(m) * 60 + int(s)


# Create your views here.


def get_tokens_for_user(user):
  # refresh = RefreshToken.for_user(user)
  access_token = create_access_token(user.id)
  refresh_token = create_refresh_token(user.id)
  # print(refresh_token)
  id = decode_refresh_token(refresh_token)
  refresh_access_token = create_access_token(id)

  return {
      'refresh': refresh_token,
      'access': refresh_access_token,
  }


def unlock_scooter(token, vin):
    print("IN UNLOCK SCOOTER =============================== ")
    url = f"https://bookings.revos.in/vehicles/{vin}/unlock"

    print("url=============================== ", url)
    print("token=============================== ", token)

    headers = {
        'token': os.getenv('bolt_app_token'),
        'authorization': token
    }
    response = requests.request("POST", url, headers=headers)
    print(response, "===================RESPONSE", response.json())
    return response


def lock_scooter(token, vin):
    url = f"https://bookings.revos.in/vehicles/{vin}/lock"
    headers = {
        'token': config('bolt_app_token'),
        'authorization': token
    }
    response = requests.request("POST", url, headers=headers)
    return response


class RegisterUserView(APIView):
    renderer_classes = [UserRenderer]

    def post(self, request, *args, **kwargs):
        if request.data:
            try:
                serializer = UserRegistrationSerializer(data=request.data)
                if serializer.is_valid():
                    serializer.save()
                    email = serializer.validated_data['email']
                    send_otp_via_email(email)
                    user = User.objects.get(email=email)
                    token = get_tokens_for_user(user)
                    payload = {
                        # "firstName": "",
                        "UID": user.id,
                        # "phone": "",
                        # "email": ""
                    }
                    # print(os.getenv("bolt_app_token"))
                    headers = {
                        'token': os.getenv("bolt_app_token")
                    }
                    url = 'https://auth.revos.in/user/register/open'
                    response = requests.request("POST", url, headers=headers, data=payload)
                    data = response.json()
                    # print(data)
                    if data.get('status') == 200:
                        bolt_id = data.get('data').get('user').get('_id')
                        bolt_token = data.get('data').get('token')
                        user.bolt_id = bolt_id
                        user.bolt_token = bolt_token
                        user.save()

                    response = {
                        "success": True,
                        "message": "User Registration Successfull, Please check your email and verify using OTP",
                        "status": status.HTTP_201_CREATED,
                        'user_id': user.id,
                        "user_name": user.user_name,
                        "user_phone": str(user.phone),
                        "user_email": user.email,
                        "is_kyc_verified": user.is_user_kyc_verified,
                        "token": token,
                        "bolt_token": user.bolt_token
                    }
                    # print('*'*20,user.bolt_token)
                    return Response(response, status=status.HTTP_201_CREATED)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                print("E ==================================", e)
                return Response({
                    "message":str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({
                "message": "Data not found"
            }, status=status.HTTP_404_NOT_FOUND)


class VerifyOTP(APIView):
    renderer_classes = [UserRenderer]

    def post(self, request, pk, *args, **kwargs):
        try:
            serializer = VerifyAccountSerializer(data=request.data)
            if serializer.is_valid():
                otp = serializer.validated_data['otp']
                user = User.objects.get(id=pk, otp=otp)
                if user:
                    user.is_email_verified = True
                    user.save()
                    token = get_tokens_for_user(user)
                    return Response({
                        "success": True,
                        "message": "your email is verified and logged in successfully",
                        'user_id': user.id,
                        "user_name": user.user_name,
                        "user_phone": str(user.phone),
                        "user_email": user.email,
                        "is_kyc_verified": user.is_user_kyc_verified,
                        "token": token,
                        "bolt_token": user.bolt_token
                    }, status=status.HTTP_200_OK)
                # return Response({
                #     "status": 400,
                #     "message": "Please enter valid otp"
                # })
                return Response({
                    "message": "Your username and otp is doesn't match!! please enter valid OTP or username"
                }, status=status.HTTP_400_BAD_REQUEST)
                # except:
            return Response({
                "message":"Something went wrong"
            }, status=status.HTTP_400_BAD_REQUEST)
        except:
            return Response({
                "message":"Please Enter Valid OTP"
            }, status=status.HTTP_400_BAD_REQUEST)


class UserLoginWithEmail(APIView):
    renderer_classes = [UserRenderer]

    def post(self, request, *ags, **kwargs):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            fcm_token = serializer.validated_data['fcm_token']
            user = User.objects.filter(email=email)
            if user:
                user_validate = authenticate(email=email, password=password)
                user = User.objects.get(email=email)
                if user.is_email_verified:
                    if user_validate:
                        token = get_tokens_for_user(user)
                        url = "https://auth.revos.in/user/login/open"
                        payload = {
                            "UID": user.id
                        }
                        headers = {
                            'token': os.getenv('bolt_app_token')
                        }
                        response_bolt = requests.request("POST", url, headers=headers, data=payload)
                        data = response_bolt.json()
                        if data.get('status') == 206 or data.get('status') == 200:
                            user_auth_token = data.get('data').get('token')
                            response={
                                "success": True,
                                "message": "User logged in Successfully",
                                "status": status.HTTP_201_CREATED,
                                'user_id': user.id,
                                "user_name": user.user_name,
                                "user_phone": str(user.phone),
                                "user_email": user.email,
                                "is_kyc_verified": user.is_user_kyc_verified,
                                "token": token,
                                "bolt_token": user_auth_token
                            }
                            user.bolt_token = user_auth_token
                            user.fcm_token=fcm_token
                            user.save()
                            return Response(response, status=status.HTTP_201_CREATED)
                        return Response(data, status=status.HTTP_400_BAD_REQUEST)
                    return Response({
                        'message': "username or password does not match!! please enter correct credentials"
                    }, status=status.HTTP_400_BAD_REQUEST)
                send_otp_via_email(user.email)
                return Response({
                    'message': "user has not verified the email, please check your email and verify it using OTP sent to your email address",
                    'user_id': user.id
                }, status.HTTP_404_NOT_FOUND)
            return Response({
                'message': "username or password does not match!! please enter correct credentials"
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class VerifyOtpLogin(APIView):
#     renderer_classes = [UserRenderer]
#
#     def post(self, request, pk, *args, **kwargs):
#         serializer = VerifyAccountSerializerLogin(data=request.data)
#         if serializer.is_valid():
#             otp = serializer.validated_data['otp']
#             try:
#                 user = User.objects.get(id=pk, otp=str(otp))
#             except:
#                 return Response({
#                     "message":"Please enter valid otp"
#                 }, status=status.HTTP_400_BAD_REQUEST)
#             if not user:
#                 return Response({
#                     "message": "Please enter valid otp"
#                 }, status=status.HTTP_400_BAD_REQUEST)
#             url = "https://auth.revos.in/user/login/open"
#             payload = {
#                 "UID": user.id
#             }
#             headers = {
#                 'token': config('bolt_app_token')
#             }
#             response_bolt = requests.request("POST", url, headers=headers, data=payload)
#             data = response_bolt.json()
#             if data.get('status') == 200:
#                 user_auth_token = data.get('data').get('token')
#                 user.bolt_token = user_auth_token
#                 user.fcm_token = serializer.validated_data['fcm_token']
#                 user.is_email_verified = True
#                 user.save()
#                 access_token = create_access_token(user.id)
#                 refresh_token = create_refresh_token(user.id)
#                 print("type ================", type(refresh_token))
#                 id = decode_refresh_token(refresh_token)
#                 refresh_access_token = create_access_token(id)
#                 return Response({
#                     "success": True,
#                     "status": status.HTTP_201_CREATED,
#                     'user_id': user.id,
#                     "user_name": user.user_name,
#                     "user_phone": str(user.phone),
#                     "user_email": user.email,
#                     "message": "logged in successfully",
#                     "is_kyc_verified": user.is_user_kyc_verified,
#                     "access": access_token,
#                     "refresh": refresh_access_token,
#                     "bolt_token": user_auth_token
#                 }, status=status.HTTP_200_OK)
#             return Response(data, status=status.HTTP_404_NOT_FOUND)
#         return Response({
#             "message":"Something wents wrong"
#         }, status=status.HTTP_404_NOT_FOUND)


class VerifyOtpLogin(APIView):
    renderer_classes = [UserRenderer]

    def post(self, request, pk, *args, **kwargs):
        serializer = VerifyAccountSerializerLogin(data=request.data)
        if serializer.is_valid():
            otp = serializer.validated_data['otp']
            try:
                user = User.objects.get(id=pk, otp=str(otp))
            except:
                return Response({
                    "message":"Please enter valid otp"
                }, status=status.HTTP_400_BAD_REQUEST)
            if not user:
                return Response({
                    "message": "Please enter valid otp"
                }, status=status.HTTP_400_BAD_REQUEST)

            url = "https://auth.revos.in/user/login/open"
            payload = {
                "UID": user.id
            }
            headers = {
                'token': os.getenv('bolt_app_token')
            }
            response_bolt = requests.request("POST", url, headers=headers, data=payload)
            data = response_bolt.json()
            if data.get('status') == 206 or data.get('status') == 200:
                user_auth_token = data.get('data').get('token')
                user.bolt_token = user_auth_token
                user.fcm_token = serializer.validated_data['fcm_token']
                user.is_email_verified = True
                user.save()
                access_token = create_access_token(user.id)
                refresh_token=create_refresh_token(user.id)
                id = decode_refresh_token(refresh_token)
                refresh_access_token = create_access_token(id)
                print("Type ================", type(access_token), type(refresh_token))
                return Response({
                    "success": True,
                    "status": status.HTTP_201_CREATED,
                    'user_id': user.id,
                    "user_name": user.user_name,
                    "user_phone": str(user.phone),
                    "user_email": user.email,
                    "message": "logged in successfully",
                    "is_kyc_verified": user.is_user_kyc_verified,
                    "token": get_tokens_for_user(user),
                    # "access_token": access_token.decode(),
                    # "refresh_access_token":refresh_access_token.decode(),
                    "bolt_token": user_auth_token
                }, status=status.HTTP_200_OK)
            return Response(data, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "message":"Something wents wrong"
        }, status=status.HTTP_404_NOT_FOUND)


class SendMobileOtp(APIView):
    renderer_classes = [UserRenderer]

    def post(self, request, *args, **kwargs):
        # account_sid = 'AC1577b26c8c36e9e0ff226217bbe2740e'
        # auth_token = '7e7f79d87fe4b9ee6e54b9486b901677'
        # client = Client(account_sid, auth_token)
        serializer = PhoneOtpSerializer(data=request.data)
        if serializer.is_valid():
            phone = "+" + str(serializer.validated_data['phone'])
            try:
                user = User.objects.get(phone=phone)
                if user:
                    send_otp_via_phone(phone=phone)
                return Response({
                    "user_id": user.id,
                    "message": "Your otp sent successfully",
                    "is_kyc_verified": user.is_user_kyc_verified,
                }, status=status.HTTP_200_OK)
            except Exception as e:
                print("e====================", str(e))
                return Response({
                    "message": str(e)
                }, status=status.HTTP_400_BAD_REQUEST)

                # phone_number = phone
                # my_otp = random.randint(1111, 9999)
                # message = client.messages.create(
                #                         body=f"Hi,Welcome to ElekGo ,{my_otp} is your one time password to proceed on ElekGo. Do not share your OTP with anyone.",
                #                         from_='+14245678409',
                #                         to=f'{phone}'
                # )
                # User.objects.filter(phone=phone).update(otp=my_otp)

            # return Response({
            #     "status":400,
            #     "message":"Something wents wrong"
            # })
        return Response({
            "message":"Something wents wrong"
        }, status=status.HTTP_400_BAD_REQUEST)


class ResendOtpSerializerView(APIView):
    renderer_classes = [UserRenderer]

    def post(self, request):
        serializer = ResendOtpSerializer(data=request.data)
        if serializer.is_valid():
            user_id = serializer.validated_data['user_id']
            email = serializer.validated_data['email']
            phone = "+" + str(serializer.validated_data['phone'])
            if email is None and phone is None:
                return Response(serializer.validated_data, status=status.HTTP_400_BAD_REQUEST)
            if email:
                try:
                    user = User.objects.get(id=user_id, email=email)
                    send_otp_via_email(user.email)
                    return Response({
                        "user_id": user.id,
                        "message": "Your otp sent successfully",
                        "email": user.email,
                        "is_kyc_verified": user.is_user_kyc_verified,
                    }, status=status.HTTP_200_OK)
                except:
                    return Response({
                        'message': 'user not found with the email and id'
                    }, status=status.HTTP_404_NOT_FOUND)
            if phone:
                try:
                    user = User.objects.get(id=user_id, phone=phone)
                    send_otp_via_phone(user.phone)
                    return Response({
                        "user_id": user.id,
                        "message": "Your otp sent successfully",
                        "phone": str(user.phone),
                        "is_kyc_verified": user.is_user_kyc_verified,
                    }, status=status.HTTP_200_OK)
                except:
                    return Response({
                        'message': 'user not found with the phone and id'
                    }, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_404_NOT_FOUND)


class FAQSerializerView(APIView):
    renderer_classes = [UserRenderer]
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        faq = FrequentlyAskedQuestions.objects.all()
        serializer = FrequentlyAskedQuestionSerializer(faq, many=True)
        return Response({'faq': serializer.data})


class UserKycVerificationSerializerView(APIView):
    renderer_classes = [UserRenderer]
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UserKycVerificationSerializer(data=request.data)
        if serializer.is_valid():
            user_id = serializer.validated_data['user_id']
            user_image = serializer.validated_data['user_image']
            user_aadhar_identification_num = serializer.validated_data['user_aadhar_identification_num']
            user_aadhar_image = serializer.validated_data['user_aadhar_image']
            user_aadhar_image_back = serializer.validated_data['user_aadhar_image_back']
            try:
                user = User.objects.get(id=user_id)
                if user:
                    user.user_image = user_image
                    user.user_aadhar_image = user_aadhar_image
                    user.user_aadhar_identification_num = user_aadhar_identification_num
                    user.user_aadhar_image_back = user_aadhar_image_back
                    user.is_user_kyc_verified = 'Pending'
                    user.save()
                return Response({
                    'message': 'Uploaded kyc details successfully',
                    'user_id': user_id,
                    'user_aadhar_identification_num': user.user_aadhar_identification_num,
                    'is_kyc_verified': user.is_user_kyc_verified
                })
            except Exception as e:
                return Response({
                    'message': str(e)
                }, status=status.HTTP_404_NOT_FOUND)
            # return Response(serializer.data, )
        return Response(serializer.errors, status.HTTP_400_BAD_REQUEST)


class VehicleReportView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = VehicleReportSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message":"your vehicle report saved successfully.please wait for an action",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        return Response({
            "message":"something wents wrong",
            "error": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"message": "Logout Successfully"}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user_id = serializer.validated_data['user_id']
            try:
                user = User.objects.get(id=user_id)
                if check_password(serializer.validated_data['old_password'], user.password):
                    user.password = make_password(serializer.validated_data['new_password'])
                    user.save()
                    return Response({"message": "password updated successfully"},
                                    status=status.HTTP_200_OK)
                return Response({"message": "old password doesn't match with your password"}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({
                    'message': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.errors, status=status.HTTP_404_NOT_FOUND)


class UpdateProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user = User.objects.get(id=request.data.get('user_id'))
            if user:
                user.user_name = request.data.get('user_name')
                user.save()
                return Response({
                    "success": True,
                    "status": status.HTTP_200_OK,
                    'user_id': user.id,
                    "user_name": user.user_name,
                    "user_phone": str(user.phone),
                    "user_email": user.email,
                    "message": "Profile updated successfully",
                    "is_kyc_verified": user.is_user_kyc_verified,
                    "token": get_tokens_for_user(user),
                    "bolt_token": user.bolt_token
                }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"message": str(e)}, status=status.HTTP_200_OK)


class CustomerSatisfactionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            user_id = request.data['user_id']
            user_details = CustomerSatisfaction.objects.get(user_id=user_id)
            serializer = CustomerSatisfactionSerializer(user_details, data=request.data)
            if serializer.is_valid():
                serializer.save()
                if str(request.data['user_is_satisfied']) == "False":
                    return Response({
                        "message": "Thank You,Your response saved successfully,Our team will connect you soon"
                    }, status=status.HTTP_200_OK)
                return Response({
                    "message": "Thank You,Your response saved successfully"
                    }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_404_NOT_FOUND)
        except:
            serializer = CustomerSatisfactionSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save()
                if str(request.data['user_is_satisfied']) == "False":
                    return Response({
                        "message": "Thank You,Your response saved successfully,Our team will connect you soon"
                    }, status=status.HTTP_200_OK)
                return Response({
                    "message": "Thank You,Your response saved successfully"
                    }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_404_NOT_FOUND)


class PaymentView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        request.data['payment_amount'] = request.data['payment_amount'].replace(',', '')
        serializer = PaymentModelSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            # user_id = serializer.validated_data['payment_user_id']
            pay_user_id = request.data['payment_user_id']
            received_amount = request.data['payment_amount']
            data = {
                "account_user_id": pay_user_id,
                "account_amount": received_amount
            }
            try:
                pay_user = UserPaymentAccount.objects.get(account_user_id=pay_user_id)
                amount = pay_user.account_amount
                final_amount = float(amount) + float(received_amount)
                UserPaymentAccount.objects.filter(account_user_id=pay_user_id).update(account_amount=final_amount)
                return Response({
                    "message": "Payment Details Saved Successfully, Your wallet has been updated"
                }, status=status.HTTP_201_CREATED)
            except Exception as E:
                serializer = UserPaymentAccountSerializer(data=data)
                if serializer.is_valid():
                    serializer.save()
                    return Response({"message": "Your wallet has been updated"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserAccountBalanceView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kargs):
        user = UserPaymentAccount.objects.filter(account_user_id=pk)
        user_payment = PaymentModel.objects.filter(payment_user_id=pk)
        if user:
            serializer = UserPaymentAccountSerializer(user, many=True)
            serializer1 = PaymentModelSerializer(user_payment, many=True)
            return Response({
                "data": serializer.data,
                "payment": serializer1.data
            })
        return Response({
            "message": "Your wallet balance is lower."
        }, status=status.HTTP_400_BAD_REQUEST)


class RideStartStopSerializerView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = RideStartStopSerializer(data=request.data)
        if serializer.is_valid():
            action = request.data.get('action')
            user_id = request.data.get('user_id')
            scooter_id = request.data.get('scooter_chassis_no')
            current_time = datetime.datetime.now().strftime("%H:%M:%S")
            try:
                user = User.objects.get(id=user_id)
                scooter = Vehicle.objects.get(vehicle_unique_identifier=scooter_id)
                print("SCOOTER ============ ", scooter)
                print("USER============ ", user)
                if action == "start":
                    print("====================In start")
                    unlock_data = unlock_scooter(user.bolt_token, scooter.vehicle_unique_identifier)
                    print("unlock_data====================unlock_data")
                    if unlock_data.status_code == 200:
                        scooter.is_unlocked = True
                        scooter.save()
                        ride = RideTable(riding_user_id=user, vehicle_id=scooter, start_time=current_time, is_ride_running=True)
                        ride.save()
                        return Response({
                                "data": [{
                                    'message': 'ride started',
                                    'ride_id': ride.id
                                }]
                        }, status=status.HTTP_200_OK)

                if action == "pause":
                    lock_data = lock_scooter(user.bolt_token, scooter.vehicle_unique_identifier)
                    if lock_data.status_code == 200:
                        ride = RideTable.objects.get(riding_user_id=user, vehicle_id=scooter, is_ride_running=True)
                        ride.pause_time = str(current_time)
                        start = datetime.datetime.strptime(str(ride.start_time), "%H:%M:%S")
                        pause = datetime.datetime.strptime(str(ride.pause_time), "%H:%M:%S")
                        delta = pause-start
                        ride.total_running_time = get_sec(str(delta))
                        ride.is_paused = True
                        ride.save()
                        related_ride = RideTimeHistory(ride_table_id=ride, pause_time=str(current_time))
                        related_ride.save()
                        return Response({
                            "data": [{
                                'message': 'ride paused',
                                'ride_id': ride.id
                            }]
                        }, status=status.HTTP_200_OK)
                if action == "resume":
                    unlock_data = unlock_scooter(user.bolt_token, scooter.vehicle_unique_identifier)
                    if unlock_data.status_code == 200:
                        ride = RideTable.objects.get(riding_user_id=user, vehicle_id=scooter, is_ride_running=True)
                        ride.resume_time = str(current_time)
                        ride.is_paused = False
                        pause = datetime.datetime.strptime(str(ride.pause_time), "%H:%M:%S")
                        resume = datetime.datetime.strptime(str(ride.resume_time), "%H:%M:%S")
                        print("pause resume =======================", pause, resume)
                        delta = resume-pause
                        related_ride = RideTimeHistory.objects.get(ride_table_id=ride, resume_time=None)
                        related_ride.resume_time = str(current_time)
                        related_ride.total_pause_resume_time = get_sec(str(delta))
                        if ride.total_pause_time == None:
                            ride.total_pause_time = get_sec(str(delta))
                        else:
                            before_resume = int(ride.total_pause_time)
                            after_resume = related_ride.total_pause_resume_time
                            ride.total_pause_time = before_resume + after_resume
                        related_ride.save()
                        ride.save()
                        return Response({
                            "data": [{
                                'message': 'ride resume',
                                'ride_id': ride.id
                            }]
                        }, status=status.HTTP_200_OK)
                if action == 'end':
                    lock_data = lock_scooter(user.bolt_token, scooter.vehicle_unique_identifier)
                    print("lock data==================", lock_data.json())
                    if lock_data.status_code == 200:
                        scooter.is_unlocked = False
                        scooter.save()
                        ride = RideTable.objects.get(riding_user_id=user, vehicle_id=scooter, is_ride_running=True)
                        ridedetails = RideTimeHistory.objects.filter(ride_table_id=ride)
                        if len(ridedetails) != 0:
                            pause = datetime.datetime.strptime(str(ride.pause_time), "%H:%M:%S")
                            resume = datetime.datetime.strptime(str(current_time), "%H:%M:%S")
                            delta = resume - pause
                            ride.resume_time = str(current_time)
                            try:
                                related_ride = RideTimeHistory.objects.get(ride_table_id=ride, resume_time=None)
                                related_ride.resume_time = str(current_time)
                                related_ride.total_pause_resume_time = get_sec(str(delta))
                                related_ride.save()
                            except Exception as e:
                                print("Exception=================", e)
                            all_rides = RideTimeHistory.objects.filter(ride_table_id=ride).aggregate(Sum('total_pause_resume_time'))
                            ride.total_pause_time = all_rides.get('total_pause_resume_time__sum')
                        ride.end_time = str(current_time)
                        ride.is_ride_end = True
                        ride.end_date = datetime.date.today()
                        ride.is_ride_running = False
                        ride.is_paused = False
                        ride.save()
                        end = datetime.datetime.strptime(str(ride.end_time), "%H:%M:%S")
                        start = datetime.datetime.strptime(str(ride.start_time), "%H:%M:%S")
                        delta = end - start
                        if ride.pause_time and ride.resume_time:
                            resume = datetime.datetime.strptime(str(ride.resume_time), "%H:%M:%S")
                            pause = datetime.datetime.strptime(str(ride.pause_time), "%H:%M:%S")
                            delta1 = resume - pause
                            ride.total_running_time = get_sec(str(delta - delta1))
                        else:
                            ride.total_running_time = get_sec(str(delta))
                        ride.save()
                        ride_pause_time_in_secondes = str(ride.total_pause_time)
                        final_time = str(ride.total_running_time)
                        total_km = 3
                        per_min_cost_on_running = round(float(ride.vehicle_id.per_min_charge) / 60, 4)
                        per_min_pause_cost = round(float(ride.vehicle_id.per_pause_charge) / 60, 4)
                        ride_pause_time_cost = float(ride_pause_time_in_secondes) * float(per_min_pause_cost) if ride.pause_time else 0
                        ride_run_time_cost = float(final_time) * float(per_min_cost_on_running)
                        total_cost = float(per_min_cost_on_running) * float(final_time) + (ride_pause_time_cost)
                        gst_cost = total_cost * 5 / 100
                        total_cost_with_gst = round(total_cost + gst_cost, 2)
                        trip_statistics = {
                            "per_minute_charges_on_running": 2.5,
                            "total_running_mins": f'{time.strftime("%M:%S", time.gmtime(int(final_time)))} Min',
                            "per_minute_charges_on_pause": 0.5,
                            "total_pause_mins": f'{time.strftime("%M:%S", time.gmtime(int(ride_pause_time_in_secondes)))} Min' if ride.total_pause_time else '00:00 Min',
                            "total_min_cost": round(ride_run_time_cost, 2),
                            "total_pause_cost": round(ride_pause_time_cost, 2),
                            "total_km": total_km,
                            "gst": '5%',
                            "gst_cost": round(gst_cost, 2),
                            "total_cost": total_cost_with_gst,
                        }
                        payment = PaymentModel(payment_user_id=user, payment_amount=-total_cost_with_gst, payment_date=datetime.date.today(), payment_note='Book Ride')
                        payment.save()
                        user_payment = UserPaymentAccount.objects.get(account_user_id=payment.payment_user_id)
                        user_payment.account_amount = float(user_payment.account_amount) - float(total_cost_with_gst)
                        user_payment.save()
                        ride.payment_id = payment
                        ride.save()
                        return Response({
                            "data": [{
                                'message': 'ride end',
                                'ride_id': ride.id,
                                'trip_statistics': trip_statistics
                            }]
                        }, status=status.HTTP_200_OK)
                    return Response({'message': 'something went wrong'}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({'message': str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_404_NOT_FOUND)


class ScanBarcodeView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        data = request.data
        if data and data.get("scooter_chassis_no"):
            try:
                scooter = Vehicle.objects.get(vehicle_unique_identifier=data.get("scooter_chassis_no"))
                if scooter.is_under_maintenance:
                    return Response(
                        {
                            'message': "This scooter is under maintenance!! please try some other scooter"
                        }, status=status.HTTP_400_BAD_REQUEST)
                if scooter.is_reserved:
                    if scooter.reserverd_user_id and scooter.reserverd_user_id.id == pk:
                        scooter.is_booked = True
                        scooter.booked_user_id = scooter.reserverd_user_id
                        scooter.save()
                        return Response(
                            {"data": [{
                                'scooter_chassis_num': scooter.vehicle_unique_identifier,
                                'battery_percentage': scooter.battery_percentage,
                                'iot_device_number': scooter.iot_device_number,
                                'scooter_number': scooter.scooter_number,
                                'battery_number': scooter.battery_number,
                                'current_location': scooter.current_location,
                                'total_km_capacity': scooter.total_km_capacity,
                                'per_min_charge': scooter.per_min_charge}]
                            }, status=status.HTTP_200_OK)
                    return Response(
                        {
                            'message': "Already Reserved, you cannot book this scooter!! please try some other scooter"
                        }, status=status.HTTP_400_BAD_REQUEST)
                user = User.objects.get(id=pk)
                scooter.is_booked = True
                scooter.booked_user_id = user
                scooter.save()
                return Response(
                    {"data":[{
                        'scooter_chassis_num': scooter.vehicle_unique_identifier,
                        'battery_percentage': scooter.battery_percentage,
                        'iot_device_number': scooter.iot_device_number,
                        'scooter_number': scooter.scooter_number,
                        'battery_number': scooter.battery_number,
                        'current_location': scooter.current_location,
                        'total_km_capacity': scooter.total_km_capacity,
                        'per_min_charge': scooter.per_min_charge}]
                    }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({
                    'message': str(e)
                }, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'scooter_chassis_no': 'This field is required'
        }, status=status.HTTP_404_NOT_FOUND)


class AllNotifications(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self,request,*args,**kwargs):
        all_notifations = NotificationModel.objects.all()
        serializer = NotificationSerializer(all_notifations,many=True)
        return Response({
            "data":serializer.data
        },status=status.HTTP_200_OK)


class AdminUserRegisterUserView(APIView):
    renderer_classes = [UserRenderer]

    def post(self, request, *args, **kwargs):
        if request.data:
            try:
                serializer = AdminUserRegistrationSerializer(data=request.data)
                if serializer.is_valid():
                    serializer.save()
                    # send_otp_via_email(serializer.validated_data['email'])
                    email = serializer.validated_data['email']
                    user = User.objects.get(email=email)
                    token = get_tokens_for_user(user)
                    payload = {
                        "firstName": "",
                        "UID": str(user.id),
                        "phone": "",
                        "email": ""
                    }
                    headers = {
                        'token': os.getenv('bolt_app_token')
                    }
                    url = 'https://auth.revos.in/user/register/open'
                    response = requests.request("POST", url, headers=headers, data=payload)
                    data = response.json()
                    if data.get('status') == 200:
                        bolt_id = data.get('data').get('user').get('_id')
                        bolt_token = data.get('data').get('token')
                        user.bolt_id = bolt_id
                        user.bolt_token = bolt_token
                        user.save()
                        response = {
                            "status_code": 201,
                            'user_id': user.id,
                            "user_name": user.user_name,
                            "user_phone": str(user.phone),
                            "user_email": str(user.email),
                            "token": token
                        }
                        return Response(response, status=status.HTTP_201_CREATED)
                response = {
                    "status_code": 400,
                    "errors": serializer.errors
                }
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({
                    "status_code": 500,
                    "message": "Something went wrong"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({
                "status_code": 404,
                "message": "Data not found"
            }, status=status.HTTP_404_NOT_FOUND)


class AdminUserLogin(APIView):
    renderer_classes = [UserRenderer]

    def post(self, request, *args, **kwargs):
        serializer = AdminUserLoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            fcm_token = serializer.validated_data['fcm_token']
            user = User.objects.filter(email=email)
            if user:
                user_validate = authenticate(email=email, password=password)
                user = User.objects.get(email=email)
                # if user.is_email_verified:
                if user_validate:
                    token = get_tokens_for_user(user)
                    url = "https://auth.revos.in/user/login/open"
                    payload = {
                        "UID": user.id
                    }
                    headers = {
                        'token': os.getenv('bolt_app_token')
                    }
                    response_bolt = requests.request("POST", url, headers=headers, data=payload)
                    data = response_bolt.json()
                    if data.get('status') == 206 or data.get('status') == 200:
                        user_auth_token = data.get('data').get('token')
                        response = {
                            "status_code": 200,
                            "message": "User logged in Successfully",
                            'user_id': user.id,
                            "user_name": user.user_name,
                            "user_phone": str(user.phone),
                            "user_email": user.email,
                            "user_role": user.user_role,
                            "token": token
                        }
                        user.bolt_token = user_auth_token
                        user.fcm_token = fcm_token
                        user.save()
                        return Response(response, status=status.HTTP_200_OK)
                    return Response(data, status=status.HTTP_400_BAD_REQUEST)
                # send_otp_via_email(user.email)
                return Response({
                    "status_code": 404,
                    'message': "user has not verified the email, please check your email and verify it using OTP sent to your email address",
                    'user_id': user.id
                }, status.HTTP_404_NOT_FOUND)
            return Response({
                "status_code": 400,
                'message': "username or password does not match!! please enter correct credentials"
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetAllAdminUsers(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self,request,*args,**kwargs):
        user = User.objects.all().exclude(user_role=5)
        data = GetAllUserSerializer(user,many=True)
        return Response({
            "data":data.data
        },status=status.HTTP_200_OK)


class GetCurrentRideTime(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = RideRunningTimeGet(data=request.data)
        if serializer.is_valid():
            try:
                ride = serializer.validated_data['ride_id']
                user = serializer.validated_data['user_id']
                scooter_chassis_no = serializer.validated_data['scooter_chassis_no']
                ride_id = RideTable.objects.get(id=ride)
                if ride_id.riding_user_id.id == user and ride_id.vehicle_id.vehicle_unique_identifier == scooter_chassis_no and ride_id.is_ride_running:
                    current_time = datetime.datetime.now().strftime("%H:%M:%S")
                    start = datetime.datetime.strptime(str(ride_id.start_time), "%H:%M:%S")
                    end = datetime.datetime.strptime(str(current_time), "%H:%M:%S")
                    if ride_id.is_paused == True:
                        delta = int(ride_id.total_running_time)
                    else:
                        if ride_id.resume_time == None:
                            delta = get_sec(str(end - start))
                        else:
                            resume = datetime.datetime.strptime(str(ride_id.resume_time), "%H:%M:%S")
                            delta = get_sec(str(end - resume)) + int(ride_id.total_running_time)
                    min, sec = divmod(delta, 60)
                    hour, min = divmod(min, 60)
                    time = '%d:%02d:%02d' % (hour, min, sec)
                    data = {
                        'ride_running_time': time
                    }
                    return Response(data=data, status=status.HTTP_200_OK)
                return Response({
                    'message': 'User Data or Vehicle Data does not match with ride data.'
                }, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({
                    'message': str(e)
                }, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_404_NOT_FOUND)


class GetAllKycUsers(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = User.objects.all().exclude(is_user_kyc_verified='NA').filter(user_role=5)
        get_pending_user_count = user.filter(is_user_kyc_verified='Pending').count()
        get_rejected_user_count = user.filter(is_user_kyc_verified='Rejected').count()
        get_approved_user_count = user.filter(is_user_kyc_verified='Approved').count()
        data = GetAllKycUserSerializer(user, many=True)
        return Response({
            'total_user_count': user.count(),
            'pending_user_count': get_pending_user_count,
            'rejected_user_count': get_rejected_user_count,
            'approved_user_count': get_approved_user_count,
            "data": data.data
        }, status=status.HTTP_200_OK)


class AcceptRejectKycDetails(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            data = request.data
            user_id = data.get('user_id')
            kyc_status = data.get('is_kyc_verified')
            user = User.objects.get(id=user_id)
            if kyc_status in ['Approved', 'Rejected']:
                user.is_user_kyc_verified = kyc_status
                user.save()
                response = {
                    'message': f'Kyc Details Updated Successfully'
                }
                return Response(response, status=status.HTTP_200_OK)
            response = {
                'message': f"Kyc status should be \'Approved', 'Rejected'"
            }
            return Response(response, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            response = {
                'message': str(e)
            }
            return Response(response, status=status.HTTP_400_BAD_REQUEST)


class GetUserKycUpdate(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            user = User.objects.get(id=pk)
            response = {
                'message': f'User Kyc has been {user.is_user_kyc_verified}'
            }
            if user.is_user_kyc_verified == 'Approved':
                return Response(response, status=status.HTTP_200_OK)
            if user.is_user_kyc_verified == 'Rejected':
                return Response(response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            return Response(response, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            response = {
                'message': str(e)
            }
            return Response(response, status=status.HTTP_404_NOT_FOUND)


class CompleteRideDetail(APIView):
    def post(self, request, pk, *args, **kwargs):
        data = request.data
        ride_id = data.get('ride_id')
        try:
            ride = RideTable.objects.get(riding_user_id=pk, id=ride_id)
            ride_pause_time_in_secondes = str(ride.total_pause_time)
            final_time = str(ride.total_running_time)
            total_km = 3
            per_min_cost_on_running = round(float(ride.vehicle_id.per_min_charge) / 60, 4)
            per_min_pause_cost = round(float(ride.vehicle_id.per_pause_charge)/60, 4)
            ride_pause_time_cost = float(ride_pause_time_in_secondes) * float(per_min_pause_cost)
            total_cost = float(per_min_cost_on_running) * float(final_time) + (ride_pause_time_cost)
            gst_cost = total_cost * 5 / 100
            response = {
                "total_cost": round(total_cost + gst_cost, 2),
                "pause_cost": round(ride_pause_time_cost, 2),
                "total_km": total_km,
                "gst": '5%',
                "gst_cost": round(gst_cost, 2),
                "per_minute_charges_on_running": 2.5,
                "per_minute_charges_on_pause": 0.5,
            }
            return Response(response, status=status.HTTP_200_OK)
        except Exception as e:
            response = {
                "message": str(e)
            }
            return Response(response, status=status.HTTP_404_NOT_FOUND)


class UnlockScooter(APIView):

    def post(self, request, pk):
        user = User.objects.get(id=pk)
        vin = Vehicle.objects.get(vehicle_unique_identifier=request.data.get('scooter_chassis_number'))
        unlock_data = unlock_scooter(user.bolt_token, vin.vehicle_unique_identifier)
        if unlock_data.status_code == 200:
            vin.is_unlocked = True
            vin.save()
            return Response(unlock_data.json(), status=status.HTTP_200_OK)
        return Response(unlock_data.json(), status=status.HTTP_400_BAD_REQUEST)


class UserRideHistory(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        ride = RideTable.objects.filter(riding_user_id=pk, is_ride_end=True)
        serializer = UserRideSerializer(ride, many=True)
        return Response({
            "data": serializer.data,
        }, status=status.HTTP_200_OK)


class UserRideDetails(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, ride_id, *args, **kwargs):
        ride = RideTable.objects.get(id=ride_id, is_ride_end=True)
        ride_data = RideTable.objects.filter(id=ride_id, is_ride_end=True)
        serializer = UserRideDetailsSerializer(ride_data, many=True)
        ride_pause_time_in_secondes = str(ride.total_pause_time)
        final_time = str(ride.total_running_time)
        total_km = 3
        per_min_cost_on_running = round(float(ride.vehicle_id.per_min_charge) / 60, 4)
        per_min_pause_cost = round(float(ride.vehicle_id.per_pause_charge) / 60, 4)
        ride_pause_time_cost = float(ride_pause_time_in_secondes) * float(per_min_pause_cost) if ride.pause_time else 0
        ride_run_time_cost = float(final_time) * float(per_min_cost_on_running)
        total_cost = float(per_min_cost_on_running) * float(final_time) + (ride_pause_time_cost)
        gst_cost = total_cost * 5 / 100
        total_cost_with_gst = round(total_cost + gst_cost, 2)
        trip_statistics = {
            "per_minute_charges_on_running": 2.5,
            "total_running_mins": f'{time.strftime("%M:%S", time.gmtime(int(final_time)))} Min',
            "per_minute_charges_on_pause": 0.5,
            "total_pause_mins": f'{time.strftime("%M:%S", time.gmtime(int(ride_pause_time_in_secondes)))} Min' if ride.total_pause_time else '00:00 Min',
            "total_min_cost": round(ride_run_time_cost, 2),
            "total_pause_cost": round(ride_pause_time_cost, 2),
            "total_km": total_km,
            "gst": '5%',
            "gst_cost": round(gst_cost, 2),
            "total_cost": total_cost_with_gst,
        }
        return Response({
            "data": serializer.data[0],
            'invoice_details': trip_statistics
        })

def locations_data(pk):
    user = User.objects.get(id=pk)
    url = 'https://bookings.revos.in/user/vehicles/all'
    headers = {
        'token': os.getenv('bolt_app_token'),
        'authorization': user.bolt_token
    }
    response = requests.request("GET", url, headers=headers)
    data = response.json()
    print(data)
    # lat_long_data = [('23.033550', '72.523570'), ('23.032380', '72.525240'), ('23.063030', '72.570240'), ('23.021840', '72.530840'), ('22.9924421', '72.4613075')]
    lat_long_data = []
    for rec in range(len(data.get('vehicles'))):
        latitude = data.get('vehicles')[rec].get('location').get('latitude')
        longitude = data.get('vehicles')[rec].get('location').get('longitude')
        vin = data.get('vehicles')[rec].get('location').get('vin')
        lat_long_data.append((latitude, longitude, vin))
    origin = lat_long_data[0][0:2]
    locations = []
    vehicle_data = {}
    for rec in range(0, len(lat_long_data)):
        dist = lat_long_data[rec][0:2]
        total_km = geodesic(origin, dist).kilometers
        vehicle = Vehicle.objects.get(vehicle_unique_identifier=lat_long_data[rec][2])
        if geolocator.reverse(dist[0] + "," + dist[1]).raw['address']['postcode'] in locations:
            new_dict = str(vehicle_data.get(geolocator.reverse(dist[0] + "," + dist[1]).raw['address']['postcode'])) + "," + str({
                # "num": rec,
                # "km": round(total_km, 2),
                # "location": geolocator.reverse(dist[0] + "," + dist[1]).raw['address']['postcode'],
                "latitude": lat_long_data[rec][0],
                "longtitude": lat_long_data[rec][1],
                'vehicle': vehicle.vehicle_unique_identifier,
                "is_reserved": vehicle.is_reserved,
                "battery_percentage": vehicle.battery_percentage,
                "max_km_capacity": vehicle.total_km_capacity
            })
            vehicle_data.update({geolocator.reverse(dist[0] + "," + dist[1]).raw['address']['postcode']: new_dict })
        else:
            locations.append(geolocator.reverse(dist[0] + "," + dist[1]).raw['address']['postcode'])
            vehicle_data.update({
                geolocator.reverse(dist[0] + "," + dist[1]).raw['address']['postcode'] : {
                    # "num": rec,
                    # "km": round(total_km, 2),
                    # "location": geolocator.reverse(dist[0] + "," + dist[1]).raw['address']['postcode'],
                    "latitude": lat_long_data[rec][0],
                    "longtitude": lat_long_data[rec][1],
                    'vehicle': vehicle.vehicle_unique_identifier,
                    "is_reserved": vehicle.is_reserved,
                    "battery_percentage": vehicle.battery_percentage,
                    "max_km_capacity": vehicle.total_km_capacity
                }
            })

        rec += 1
    return vehicle_data


class GetAvailableVehicles(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        all_data = []
        loc = locations_data(pk)
        # for rec in loc:
            # scooter = ast.literal_eval(loc[rec]) if type(loc[rec]) == str else [loc[rec]]
        #     all_data.append({
        #         "location_stand": geolocator.reverse(scooter[0].get('latitude') + "," + scooter[0].get('longtitude'))[0],
        #         "latitude": scooter[0].get('latitude'),
        #         "longitude": scooter[0].get('longtitude'),
        #         "scooter_data": scooter
        #     })
        # return Response({'vehicle_data': all_data }, status=status.HTTP_200_OK)
        all_data = {
            "vehicle_data": [
                {
                    "location_stand": "Ghatlodiya, Ahmedabad, Ahmedabad City Taluka, Ahmedabad District, Gujarat, 380001, India",
                    "latitude": "23.07608",
                    "longitude": "72.52638",
                    "scooter_data": [
                        {
                            "latitude": "23.07608",
                            "longtitude": "72.52638",
                            "vehicle": "WCM202100002",
                            "is_reserved": True,
                            "battery_percentage": 50,
                            "max_km_capacity": "25/Km"
                        },
                        {
                            "latitude": "23.07608",
                            "longtitude": "72.52638",
                            "vehicle": "WCM202100002",
                            "is_reserved": True,
                            "battery_percentage": 20,
                            "max_km_capacity": "25/Km"
                        },
                        {
                            "latitude": "23.07608",
                            "longtitude": "72.52638",
                            "vehicle": "WCM202100002",
                            "is_reserved": False,
                            "battery_percentage": 50,
                            "max_km_capacity": "25/Km"
                        },
                        {
                            "latitude": "23.07608",
                            "longtitude": "72.52638",
                            "vehicle": "WCM202100002",
                            "is_reserved": False,
                            "battery_percentage": 30,
                            "max_km_capacity": "25/Km"
                        }
                    ]
                },
                {
                    "location_stand": "Gandhinagar-Sarkhej Highway, Gandhinagar, Gandhinagar Taluka, Gandhinagar District, Gujarat, 382423, India",
                    "latitude": "23.18250",
                    "longitude": "72.59683",
                    "scooter_data": [
                        {
                            "latitude": "23.18250",
                            "longtitude": "72.59683",
                            "vehicle": "WCM2021002974",
                            "is_reserved": False,
                            "battery_percentage": 50,
                            "max_km_capacity": "25/Km"
                        }
                    ]
                },
                {
                    "location_stand": "Iscon, Gandhinagar-Sarkhej Highway, Gujarat, 382423, India",
                    "latitude": "23.0202434",
                    "longitude": "72.5797426",
                    "scooter_data": [

                    ]
                },
                {
                    "location_stand": "Panjrapol, Ahmedabad, Ahmedabad City Taluka, Ahmedabad District, Gujarat, 380001, India",
                    "latitude": "23.07685",
                    "longitude": "72.52658",
                    "scooter_data": [
                        {
                            "latitude": "23.07608",
                            "longtitude": "72.52638",
                            "vehicle": "WCM202100002",
                            "is_reserved": True,
                            "battery_percentage": 50,
                            "max_km_capacity": "25/Km"
                        },
                        {
                            "latitude": "23.07608",
                            "longtitude": "72.52638",
                            "vehicle": "WCM202100002",
                            "is_reserved": True,
                            "battery_percentage": 20,
                            "max_km_capacity": "25/Km"
                        },
                        {
                            "latitude": "23.07608",
                            "longtitude": "72.52638",
                            "vehicle": "WCM202100002",
                            "is_reserved": False,
                            "battery_percentage": 50,
                            "max_km_capacity": "25/Km"
                        },
                    ]
                },
            ]
        }
        return Response(all_data, status=status.HTTP_200_OK)


class GetAllUsersData(APIView, LimitOffsetPagination):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    page_size = 20
    page_size_query_param = 'count'

    def get(self, request):
        user = User.objects.filter(user_role=5).count()
        users_list = User.objects.filter(user_role=5)
        results = self.paginate_queryset(users_list, request, view=self)
        serializer = GetAllUsersSerializer(results, many=True)
        return Response({
            'Total_Users': user,
            'next_limit': self.limit + 20,
            'next_offset': self.offset + 20,
            'previous_limit': self.limit - 20,
            'previous_offset': self.offset - 20,
            'Users_details': serializer.data
        })


class ResetPasswordView(APIView):
    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        user = User.objects.filter(email=email)
        if user:
            generated_otp = send_otp_session_via_email(email)
            session_data = SessionStore()
            session_data['otp'] = generated_otp
            session_data['email'] = email
            session_data.create()
            return Response({
                "msg": "successfull",
                "session_key": session_data.session_key
            })
        return Response({
            "msg": "You are not a registered user,please register"
        })


class VeifyOtpForPasswordReset(APIView):
    def post(self, request, *args, **kwargs):
        received_otp = request.data.get('otp')
        session_id = request.data.get('session_id')
        session_stored_data = SessionStore(session_key=session_id)
        try:
            data = session_stored_data['otp']
        except:
            return Response({
                "msg": "Your OTP has been expired,Please generate otp once again"
            }, status=status.HTTP_403_FORBIDDEN)
        if int(received_otp) == int(data):
            return Response({
                "msg": "Your email verified successfully,Please Create a new password"
            }, status=status.HTTP_200_OK)
        return Response({
            "msg": "Please Enter a valid otp"
        }, status=status.HTTP_400_BAD_REQUEST)


class CreateNewPassword(APIView):

    def post(self, request):
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')
        session_id = request.data.get('session_id')
        session_stored_data = SessionStore(session_key=session_id)
        try:
            data = session_stored_data['email']
        except:
            return Response({
                "msg": "User not found or session expired"
            }, status=status.HTTP_404_NOT_FOUND)
        user = User.objects.get(email=data)
        if user and new_password == confirm_password:
            user.set_password(new_password)
            user.save()
            return Response({
                "msg": "password updated successfully"
            }, status=status.HTTP_200_OK)
        return Response({
            "msg": "something went wrong"
        }, status=status.HTTP_400_BAD_REQUEST)

