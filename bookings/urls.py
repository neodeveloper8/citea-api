from rest_framework.routers import DefaultRouter

from .views import BookingViewSet, ReviewResponseViewSet, ReviewViewSet

router = DefaultRouter()
router.register("bookings", BookingViewSet, basename="booking")
router.register("reviews", ReviewViewSet, basename="review")
router.register("review-responses", ReviewResponseViewSet, basename="review-response")
urlpatterns = router.urls
