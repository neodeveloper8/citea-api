from rest_framework.routers import DefaultRouter

from .views import BookingViewSet, ReviewViewSet

router = DefaultRouter()
router.register("bookings", BookingViewSet, basename="booking")
router.register("reviews", ReviewViewSet, basename="review")
urlpatterns = router.urls
