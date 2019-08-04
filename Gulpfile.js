'use strict';

let gulp = require('gulp');
let less = require('gulp-less');
let sass = require('gulp-sass');

gulp.task('less', function () {
    return gulp.src('./less/**/*.less')
        .pipe(less())
        .pipe(gulp.dest('./css'));
});

gulp.task('sass', function () {
    return gulp.src(['./**/*.scss', '!node_modules/**/*'])
        .pipe(sass())
        .pipe(gulp.dest('./'));
});
