from rest_framework.routers import DefaultRouter

from .views import (
    BusinessImageViewSet,
    BusinessViewSet,
    CategoryViewSet,
    ServiceViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("businesses", BusinessViewSet, basename="business")
router.register("services", ServiceViewSet, basename="service")
router.register("business-images", BusinessImageViewSet, basename="business-image")

urlpatterns = router.urls
